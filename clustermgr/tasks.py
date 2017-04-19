import os
import ldap
import time
import StringIO
import json
import re
from datetime import datetime

import requests
from fabric.api import run, execute, cd, put
from fabric.context_managers import settings
from fabric.contrib.files import exists

from .application import celery, db, wlogger, app
from .models import LDAPServer, AppConfiguration, KeyRotation, OxauthServer
from .ldaplib import ldap_conn, search_from_ldap
from .utils import decrypt_text, random_chars
from .ox11 import generate_key, delete_key
from .keygen import generate_jks

ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)


@celery.task(bind=True)
def initialize_provider(self, server_id):
    initialized = False
    server = LDAPServer.query.get(server_id)
    appconfig = AppConfiguration.query.get(1)
    dn = appconfig.replication_dn
    replication_user = [
        ('objectclass', [r'person']),
        ('cn', [r'{}'.format(
            dn.replace("cn=", "").replace(",o=gluu", ""))]),
        ('sn', [r'gluu']),
        ('userpassword', [str(appconfig.replication_pw)])
        ]

    # Step 1: Connection
    wlogger.log(self.request.id, 'Connecting to {}'.format(server.hostname))
    try:
        con = ldap.initialize('ldap://{}:{}'.format(
            server.hostname, server.port))
        if server.starttls:
            con.start_tls_s()
        con.bind_s('cn=directory manager,o=gluu', server.admin_pw)
        wlogger.log(self.request.id, 'Connection established.', 'success',
                    step='conn')
    except ldap.LDAPError as e:
        if type(e.message) == dict and 'desc' in e.message:
            wlogger.log(self.request.id, e.message['desc'], 'error',
                        step='conn')
        else:
            wlogger.log(self.request.id, "%s" % e, 'error', step='conn')

    # Step 2: Add replication user
    wlogger.log(self.request.id, 'Adding the replication user.')
    try:
        con.add_s(dn, replication_user)
        wlogger.log(self.request.id, 'Replication user added.', 'success',
                    step='add')
    except ldap.ALREADY_EXISTS:
        con.delete_s(dn)
        con.add_s(dn, replication_user)
        wlogger.log(self.request.id, 'Replication user added.', 'success',
                    step='add')
    except ldap.LDAPError as e:
        if type(e.message) == dict and 'desc' in e.message:
            wlogger.log(self.request.id, e.message['desc'], 'error',
                        step='add')
        else:
            wlogger.log(self.request.id, "%s" % e, 'error', step='add')
    finally:
        con.unbind()

    # Step 3: Reconnect as replication user
    wlogger.log(self.request.id, 'Authenticating as the Replicaiton DN.')
    try:
        con = ldap.initialize('ldap://{}:{}'.format(
            server.hostname, server.port))
        if server.starttls:
            con.start_tls_s()
        con.bind_s(dn, appconfig.replication_pw)
        wlogger.log(self.request.id, 'Reconnecting as the replication user.',
                    'success', step='recon')
        initialized = True
    except ldap.LDAPError as e:
        if type(e.message) == dict and 'desc' in e.message:
            wlogger.log(self.request.id, e.message['desc'], 'error',
                        step='recon')
        else:
            wlogger.log(self.request.id, "%s" % e, 'error', step='recon')
    finally:
        con.unbind()

    if initialized:
        server.initialized = True
        db.session.add(server)
        db.session.commit()


@celery.task(bind=True)
def replicate(self):
    taskid = self.request.id
    dn = 'cn=testentry,o=gluu'
    replication_user = [
        ('objectclass', ['person']),
        ('cn', ['testentry']),
        ('sn', ['gluu']),
        ]

    wlogger.log(taskid, 'Listing all providers')
    providers = LDAPServer.query.filter_by(role="provider").all()
    wlogger.log(taskid, 'Available providers: {}'.format(len(providers)))

    for provider in providers:
        # connect to the server
        procon = ldap.initialize('ldap://{}:{}'.format(
            provider.hostname, provider.port))
        try:
            if provider.starttls:
                procon.start_tls_s()
            procon.bind_s('cn=directory manager,o=gluu', provider.admin_pw)
            wlogger.log(taskid, 'Connecting to the provider: {}'.format(
                provider.hostname), 'success')
            # add a entry to the server
            procon.add_s(dn, replication_user)
            wlogger.log(taskid,
                        'Adding the test entry {} to the provider'.format(dn),
                        'success')
        except ldap.LDAPError as e:
            wlogger.log(taskid,
                        'Failed to add test data to provider. {}'.format(e),
                        'error')
            continue

        consumers = provider.consumers
        wlogger.log(taskid,
                    'Listing consumers linked to the provider {}'.format(
                        provider.hostname))
        # get list of all the consumers
        for consumer in consumers:
            wlogger.log(taskid, 'Verifying data in consumers: {} of {}'.format(
                consumers.index(consumer)+1, len(consumers)))
            con = ldap.initialize('ldap://{}:{}'.format(consumer.hostname,
                                                        consumer.port))
            try:
                if consumer.starttls:
                    con.start_tls_s()
                con.bind_s('cn=directory manager,o=gluu', consumer.admin_pw)
                wlogger.log(taskid, 'Connecting to the consumer: {}'.format(
                    consumer.hostname), 'success')
            except ldap.LDAPError as e:
                wlogger.log(taskid, 'Failed to connect to {0}. {1}'.format(
                                    consumer.hostname, e), 'error')
                continue

            # fetch the data from each consumer and verify the new entry exists
            for i in range(5):
                if con.compare_s(dn, 'sn', 'gluu'):
                    wlogger.log(taskid,
                                'Test data is replicated and available.',
                                'success')
                    break
                else:
                    wlogger.log(taskid,
                                'Test data not found. Retrying in 3 secs.',
                                'error')
                    time.sleep(3)
            con.unbind()

        # delete the entry from the provider
        persists = False
        try:
            procon.delete_s(dn)
            persists = procon.compare_s(dn, 'sn', 'gluu')
            if persists:
                wlogger.log(taskid, 'Delete operation failed. Data exists.',
                            'error')
        except ldap.NO_SUCH_OBJECT:
            wlogger.log(taskid, 'Deleting test data from provider: {}'.format(
                provider.hostname), 'success')
        except ldap.LDAPError as e:
            wlogger.log(taskid,
                        'Failed to delete test data from provider: {}'.format(
                            provider.hostname), 'error')
        finally:
            procon.unbind()

        # verify the data is removed from the consumers
        for consumer in consumers:
            wlogger.log(
                taskid,
                "Verifying data is removed from consumers: {} of {}".format(
                    consumers.index(consumer)+1, len(consumers)))
            con = ldap.initialize('ldap://{}:{}'.format(consumer.hostname,
                                                        consumer.port))
            persists = False
            try:
                if consumer.starttls:
                    con.start_tls_s()
                persists = con.compare_s(dn, 'sn', 'gluu')
                if persists:
                    wlogger.log(
                        taskid,
                        'Failed to remove test data from consumer: {}'.format(
                            consumer.hostname), 'error')
                else:
                    wlogger.log(
                        taskid,
                        'Test data removed from the consumer: {}'.format(
                            consumer.hostname), 'success')
            except ldap.LDAPError as e:
                wlogger.log(
                    taskid, 'Failed to test consumer: {0}. Error: {1}'.format(
                        consumer.hostname, e), 'error')
            finally:
                con.unbind()

    wlogger.log(taskid, 'Replication test Complete.', 'success')


def run_command(taskid, command):
    outlog = StringIO.StringIO()
    errlog = StringIO.StringIO()

    wlogger.log(taskid, command, "debug")
    output = run(command, stdout=outlog, stderr=errlog)
    if outlog.getvalue():
        wlogger.log(taskid, outlog.getvalue(), "debug")
    if errlog.getvalue():
        wlogger.log(taskid, errlog.getvalue(), "error")

    return output


def generate_slapd(taskid, conffile):
    wlogger.log(taskid, "Creating Data and Schema Directories for LDAP")
    conf = open(conffile, 'r')
    for line in conf:
        if re.match('^directory', line):
            folder = line.split()[1]
            run_command(taskid, 'mkdir -p '+folder)

    run_command(taskid, 'mkdir -p /opt/gluu/schema/openldap')
    run_command(taskid, 'mkdir -p /opt/gluu/schema/others')

    wlogger.log(taskid, "Copying Schema files to server")
    gluu_schemas = os.listdir(os.path.join(app.static_folder, 'schema'))
    for schema in gluu_schemas:
        out = put(os.path.join(app.static_folder, 'schema', schema),
                  "/opt/gluu/schema/openldap/"+schema)
        wlogger.log(taskid, out, "debug")

    schemas = os.listdir(app.config['SCHEMA_DIR'])
    if len(schemas):
        for schema in schemas:
            out = put(os.path.join(app.config['SCHEMA_DIR'], schema),
                      "/opt/gluu/schema/others/"+schema)
            wlogger.log(taskid, out, "debug")

    wlogger.log(taskid, "Copying slapd.conf file to remote server")
    out = put(conffile, '/opt/symas/etc/openldap/slapd.conf')
    if out.failed:
        wlogger.log(taskid, "Failed to copy the slapd.conf file", "error")

    wlogger.log(taskid, "Checking status of LDAP server")
    status = run_command(taskid, 'service solserver status')

    if 'is running' in status:
        wlogger.log(taskid, "Stopping LDAP Server")
        run_command(taskid, 'service solserver stop')

    with cd('/opt/symas/etc/openldap/'):
        wlogger.log(taskid, "Generating slapd.d Online Configuration")
        run_command(taskid, 'rm -rf slapd.d')
        run_command(taskid, 'mkdir slapd.d')
        run_command(taskid, '/opt/symas/bin/slaptest -f slapd.conf -F slapd.d')

    wlogger.log(taskid, "Starting LDAP server")
    log = run_command(taskid, 'service solserver start')
    if 'failed' in log:
        wlogger.log(taskid, "Debugging slapd...")
        run_command(taskid, "/opt/symas/lib64/slapd -d 1 "
                    "-f /opt/symas/etc/openldap/slapd.conf")


def chcmd(chdir, command):
    # chroot /chroot_dir /bin/bash -c "<command>"
    return 'chroot /opt/{0} /bin/bash -c "{1}"'.format(chdir, command)


def gen_slapd_gluu(taskid, conffile, version):
    sloc = 'gluu-server-'+version

    wlogger.log(taskid, "\n===>  Copying slapd.conf file to remote server")
    out = put(conffile, '/opt/'+sloc+'/opt/symas/etc/openldap/slapd.conf')
    if out.failed:
        wlogger.log(taskid, "Failed to copy the slapd.conf file", "error")

    wlogger.log(taskid, "\n===>  Checking status of LDAP server")
    status = run_command(taskid, chcmd(sloc, 'service solserver status'))

    if 'is running' in status:
        wlogger.log(taskid, "\n===>  Stopping LDAP Server")
        run_command(taskid, chcmd(sloc, 'service solserver stop'))

    with cd('/opt/'+sloc+'/opt/symas/etc/openldap/'):
        wlogger.log(taskid, "\n===>  Generating slad.d Online Configuration")
        run_command(taskid, 'rm -rf slapd.d')
        run_command(taskid, 'mkdir slapd.d')

    run_command(taskid, chcmd(
        sloc, '/opt/symas/bin/slaptest -f /opt/symas/etc/openldap/slapd.conf '
        ' -F /opt/symas/etc/openldap/slapd.d'))

    wlogger.log(taskid, "\n===>  Starting LDAP server")
    log = run_command(taskid, chcmd(sloc, 'service solserver start'))
    if 'failed' in log:
        wlogger.log(taskid, "\n===>  Debugging slapd...")
        run_command(taskid, chcmd(sloc, "/opt/symas/lib64/slapd -d 1 "
                    "-f /opt/symas/etc/openldap/slapd.conf"))


@celery.task(bind=True)
def setup_server(self, server_id, conffile):
    server = LDAPServer.query.get(server_id)
    host = "root@{}".format(server.hostname)
    if server.gluu_server:
        with settings(warn_only=True):
            execute(gen_slapd_gluu, self.request.id, conffile,
                    server.gluu_version, hosts=[host])
    else:
        with settings(warn_only=True):
            execute(generate_slapd, self.request.id, conffile, hosts=[host])


def check_provider_requirements(taskid, server, conffile):
    # 1. OpenLDAP is installed
    if exists('/opt/symas/bin/slaptest'):
        wlogger.log(taskid, 'Checking if OpenLDAP is installed', 'success')
    else:
        wlogger.log(taskid, 'Cheking if OpenLDAP is installed', 'fail')
        wlogger.log(taskid, 'Kindly install OpenLDAP on the server and refresh'
                    ' this page to try setup again.')
        return
    # 2. symas-openldap.conf file exists
    if exists('/opt/symas/etc/openldap/symas-openldap.conf'):
        wlogger.log(taskid, 'Checking symas-openldap.conf exists', 'success')
    else:
        wlogger.log(taskid, 'Checking if symas-openldap.conf exists', 'fail',
                    debug_msg='Configure OpenLDAP with /opt/gluu/etc/openldap'
                    '/symas-openldap.conf')
    # 3. Certificates
    if server.tls_cacert:
        if exists(server.tls_cacert):
            wlogger.log(taskid, 'Checking TLS CA Certificate', 'success')
        else:
            wlogger.log(taskid, 'Checking TLS CA Certificate', 'fail')
    if server.tls_servercert:
        if exists(server.tls_servercert):
            wlogger.log(taskid, 'Checking TLS Server Certificate', 'success')
        else:
            wlogger.log(taskid, 'Checking TLS Server Certificate', 'fail')
    if server.tls_serverkey:
        if exists(server.tls_serverkey):
            wlogger.log(taskid, 'Checking TLS Server Key', 'success')
        else:
            wlogger.log(taskid, 'Checking TLS Server Key', 'fail')
    # 4. Schema files
    conf = open(conffile, 'r')
    wlogger.log(taskid, 'Checking for schema files included in slapd.conf')
    for line in conf:
        if re.match('^include*', line):
            schemafile = line.split()[1]
            # gluu.schema and custom.schema will be added during the setup
            if 'gluu/schema/openldap/gluu.schema' in schemafile or \
                    'gluu/schema/openldap/custom.schema' in schemafile:
                        continue
            if exists(schemafile):
                wlogger.log(taskid, '==> %s' % schemafile, 'success')
            else:
                wlogger.log(taskid, '==> %s' % schemafile, 'fail')
    conf.close()


@celery.task(bind=True)
def perform_provider_checks(self, server_id, conffile):
    server = LDAPServer.query.get(server_id)
    host = "root@{}".format(server.hostname)
    with settings(warn_only=True):
        execute(check_provider_requirements, self.request.id, server, conffile,
                hosts=[host])


def modify_oxauth_config(kr, pub_keys=None, openid_jks_pass=""):
    server = LDAPServer.query.filter_by(role="provider").first()

    pub_keys = pub_keys or []
    if not pub_keys:
        return

    with ldap_conn(server.hostname, server.port, "cn=directory manager,o=gluu",
                   server.admin_pw, server.starttls) as conn:
        # base DN for oxAuth config
        oxauth_base = ",".join([
            "ou=oxauth",
            "ou=configuration",
            "inum={}".format(kr.inum_appliance),
            "ou=appliances",
            "o=gluu",
        ])
        dn, attrs = search_from_ldap(conn, oxauth_base)

        # search failed due to missing entry
        if not dn:
            return

        # oxRevision is increased to mark update
        ox_rev = str(int(attrs["oxRevision"][0]) + 1)

        # update public keys if necessary
        keys_conf = json.loads(attrs["oxAuthConfWebKeys"][0])
        keys_conf["keys"] = pub_keys
        serialized_keys_conf = json.dumps(keys_conf)

        dyn_conf = json.loads(attrs["oxAuthConfDynamic"][0])
        dyn_conf.update({
            "keyRegenerationEnabled": False,  # always set to False
            "keyRegenerationInterval": kr.interval * 24,
            "defaultSignatureAlgorithm": "RS512",
        })

        if kr.type == "oxeleven":
            dyn_conf.update({
                "oxElevenGenerateKeyEndpoint": "{}/oxeleven/rest/oxeleven/generateKey".format(kr.oxeleven_url),  # noqa
                "oxElevenSignEndpoint": "{}/oxeleven/rest/oxeleven/sign".format(kr.oxeleven_url),  # noqa
                "oxElevenVerifySignatureEndpoint": "{}/oxeleven/rest/oxeleven/verifySignature".format(kr.oxeleven_url),  # noqa
                "oxElevenDeleteKeyEndpoint": "{}/oxeleven/rest/oxeleven/deleteKey".format(kr.oxeleven_url),  # noqa
                "oxElevenJwksEndpoint": "{}/oxeleven/rest/oxeleven/jwks".format(kr.oxeleven_url),  # noqa
                "oxElevenTestModeToken": decrypt_text(kr.oxeleven_token, kr.oxeleven_token_key, kr.oxeleven_token_iv),  # noqa
                "webKeysStorage": "pkcs11",
            })
        else:
            dyn_conf.update({
                "webKeysStorage": "keystore",
                "keyStoreSecret": openid_jks_pass,
            })
        serialized_dyn_conf = json.dumps(dyn_conf)

        # list of attributes need to be updated
        modlist = [
            (ldap.MOD_REPLACE, "oxRevision", ox_rev),
            (ldap.MOD_REPLACE, "oxAuthConfWebKeys", serialized_keys_conf),
            (ldap.MOD_REPLACE, "oxAuthConfDynamic", serialized_dyn_conf),
        ]

        # update the attributes
        conn.modify_s(dn, modlist)
        return True


@celery.task(bind=True)
def rotate_pub_keys(t):
    javalibs_dir = celery.conf["JAVALIBS_DIR"]
    jks_path = celery.conf["JKS_PATH"]
    kr = KeyRotation.query.first()

    if not kr:
        print "unable to find key rotation data from database; skipping task"
        return

    # do the key rotation background task
    _rotate_keys(kr, javalibs_dir, jks_path)


def _rotate_keys(kr, javalibs_dir, jks_path):
    pub_keys = []
    openid_jks_pass = random_chars()

    if kr.type == "oxeleven":
        token = decrypt_text(kr.oxeleven_token, kr.oxeleven_token_key,
                             kr.oxeleven_token_iv)
        kid = kr.oxeleven_kid

        try:
            # delete old keys first
            print "deleting old keys"
            status_code, out = delete_key(kr.oxeleven_url, kid, token)
            if status_code == 200 and out["deleted"]:
                kr.oxeleven_kid = ""
            elif status_code == 401:
                print "insufficient access to call oxEleven API"

            # obtain new keys
            print "obtaining new keys"
            status_code, out = generate_key(kr.oxeleven_url, token=token)
            if status_code == 200:
                kr.oxeleven_kid = out["kid"]
                pub_keys = [out]
            elif status_code == 401:
                print "insufficient access to call oxEleven API"
            else:
                print "unable to obtain the keys from oxEleven; " \
                      "status code={}".format(status_code)
        except requests.exceptions.ConnectionError:
            print "unable to establish connection to oxEleven; skipping task"
    else:
        out, err, retcode = generate_jks(
            openid_jks_pass, javalibs_dir, jks_path,
        )
        if retcode == 0:
            json_out = json.loads(out)
            pub_keys = json_out["keys"]
        else:
            print err

    # update LDAP entry
    if pub_keys and modify_oxauth_config(kr, pub_keys, openid_jks_pass):
        print "pub keys has been updated"
        kr.rotated_at = datetime.utcnow()
        db.session.add(kr)
        db.session.commit()

        if kr.type == "jks":
            def _copy_jks(path, hostname):
                out = put(path, kr.jks_remote_path)
                if out.failed:
                    print "unable to copy JKS file to " \
                        "oxAuth server {}".format(hostname)
                else:
                    print "JKS file has been copied " \
                        "to {}".format(hostname)

            for server in OxauthServer.query:
                host = "root@{}".format(server.hostname)
                with settings(warn_only=True):
                    execute(_copy_jks, jks_path, server.hostname, hosts=[host])


@celery.task
def schedule_key_rotation():
    kr = KeyRotation.query.first()

    if not kr:
        print "unable to find key rotation data from database; skipping task"
        return

    if not kr.should_rotate():
        print "key rotation task will be executed " \
              "approximately at {} UTC".format(kr.next_rotation_at)
        return

    # do the key rotation background task
    javalibs_dir = celery.conf["JAVALIBS_DIR"]
    jks_path = celery.conf["JKS_PATH"]
    _rotate_keys(kr, javalibs_dir, jks_path)


# disabled for backward-compatibility with celery 3.x
#@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        celery.conf['SCHEDULE_REFRESH'],
        schedule_key_rotation.s(),
        name='add every 30',
    )
