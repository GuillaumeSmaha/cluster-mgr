import os
import sys
import ldap
import StringIO
import json
import re
from datetime import datetime

import requests
from fabric.api import run, execute, cd, put, env, get
from fabric.context_managers import settings
from fabric.contrib.files import exists
from ldap.modlist import modifyModlist

from .application import celery, db, wlogger, app
from .models import LDAPServer, AppConfiguration, KeyRotation, OxauthServer
from .ldaplib import ldap_conn, search_from_ldap
from .utils import decrypt_text, random_chars
from .ox11 import generate_key, delete_key
from .keygen import generate_jks

ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)


class FabricException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

env.abort_exception = FabricException


def starttls(server):
    return server.protocol == 'starttls'


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


def import_ldif(taskid, ldiffile):
    wlogger.log(taskid, "Copying {0} to /tmp/init.ldif".format(ldiffile),
                "debug")
    put(ldiffile, '/tmp/init.ldif')
    run_command(taskid, 'service solserver stop')
    run_command(taskid, '/opt/symas/bin/slapadd -b o=gluu -l /tmp/init.ldif')
    run_command(taskid, 'service solserver start')
    run_command(taskid, 'rm /tmp/init.ldif')


@celery.task(bind=True)
def initialize_provider(self, server_id, use_ldif):
    initialized = False
    s = LDAPServer.query.get(server_id)
    rootuser = 'cn=directory manager,o=gluu'
    appconfig = AppConfiguration.query.get(1)
    repdn = appconfig.replication_dn
    taskid = self.request.id
    replication_user = [
        ('objectclass', [r'person']),
        ('cn', [r'{}'.format(
            repdn.replace("cn=", "").replace(",o=gluu", ""))]),
        ('sn', [r'gluu']),
        ('userpassword', [str(appconfig.replication_pw)])
        ]

    if use_ldif:
        host = "root@{}".format(s.hostname)
        ldiffile = os.path.join(app.config['LDIF_DIR'],
                                "{0}_init.ldif".format(server_id))
        with settings(warn_only=True):
            wlogger.log(taskid, "Importing the LDIF file")
            execute(import_ldif, self.request.id, ldiffile, hosts=[host])

    # Step 1: Add the Replication User DN
    wlogger.log(taskid, 'Connecting to {}'.format(s.hostname))
    with ldap_conn(s.hostname, s.port, rootuser, s.admin_pw, starttls(s)) \
            as con:
        try:
            con.add_s(repdn, replication_user)
            wlogger.log(taskid, 'Replication user added.', 'success')
        except ldap.ALREADY_EXISTS:
            con.delete_s(repdn)
            con.add_s(repdn, replication_user)
            wlogger.log(taskid, 'Replication user added.', 'success')
        except ldap.LDAPError as e:
            wlogger.log(taskid, "Failed to add Replication user", "fail")
            return
    # Step 2: Reconnect as replication user
    try:
        con = ldap.initialize('ldap://{}:{}'.format(s.hostname, s.port))
        if s.protocol == 'starttls':
            con.start_tls_s()
        con.bind_s(repdn, appconfig.replication_pw)
        wlogger.log(taskid, "Authenticating as the Replicaiton DN.", "success")
        initialized = True
    except ldap.SERVER_DOWN:
        con = ldap.initialize('ldaps://{}:{}'.format(s.hostname, s.port))
        con.bind_s(repdn, appconfig.replication_pw)
        wlogger.log(taskid, "Authenticating as the Replicaiton DN.", "success")
        initialized = True
    except ldap.LDAPError as e:
        wlogger.log(taskid, "%s" % e, 'error')
    finally:
        con.unbind()

    if initialized:
        s.initialized = True
        db.session.add(s)
        db.session.commit()


@celery.task(bind=True)
def replicate(self):
    taskid = self.request.id
    wlogger.log(taskid, 'Listing all providers')
    providers = LDAPServer.query.filter_by(role="provider").all()
    rootdn = "cn=directory manager,o=gluu"
    dn = 'cn=testentry,o=gluu'
    replication_user = [
        ('objectclass', ['person']),
        ('cn', ['testentry']),
        ('sn', ['gluu']),
        ]

    wlogger.log(taskid, 'Available providers: {}'.format(len(providers)),
                "debug")
    for provider in providers:
        try:
            with ldap_conn(provider.hostname, provider.port, rootdn,
                           provider.admin_pw, starttls(provider)) as con:
                con.add_s(dn, replication_user)
            wlogger.log(taskid, "Adding test data to provider {0}".format(
                provider.hostname), "success")
        except:
            wlogger.log(taskid, "Adding test data to provider {0}".format(
                provider.hostname), "fail")
            t, v = sys.exc_info()[:2]
            wlogger.log(taskid, "%s %s" % (t, v), "debug")

        consumers = provider.consumers
        wlogger.log(taskid,
                    'Listing consumers of provider %s' % provider.hostname)
        # Check the consumers 
        for consumer in consumers:
            wlogger.log(taskid, 'Verifying data in consumers: {} of {}'.format(
                consumers.index(consumer)+1, len(consumers)))
            try:
                with ldap_conn(consumer.hostname, consumer.port, rootdn,
                               consumer.admin_pw, starttls(provider)) as con:
                    if con.compare_s(dn, 'sn', 'gluu'):
                        wlogger.log(
                            taskid,
                            'Test data is replicated and available', 'success')
            except ldap.NO_SUCH_OBJECT:
                wlogger.log(taskid, 'Test data is NOT replicated.', 'fail')
            except ldap.LDAPError as e:
                wlogger.log(taskid, 'Failed to connect to {0}. {1}'.format(
                                    consumer.hostname, e), 'error')

        # delete the entry from the provider
        try:
            with ldap_conn(provider.hostname, provider.port, rootdn,
                           provider.admin_pw, starttls(provider)) as con:
                con.delete_s(dn)
                if con.compare_s(dn, 'sn', 'gluu'):
                    wlogger.log(taskid, 'Delete operation failed. Data exists',
                                'error')
        except ldap.NO_SUCH_OBJECT:
            wlogger.log(taskid, 'Deleting test data from provider: {}'.format(
                provider.hostname), 'success')
        except:
            t, v = sys.exc_info()[:2]
            wlogger.log(taskid, "%s %s" % (t, v), "debug")

        # verify the data is removed from the consumers
        for consumer in consumers:
            wlogger.log(
                taskid,
                "Verifying data is removed from consumers: {} of {}".format(
                    consumers.index(consumer)+1, len(consumers)))
            try:
                with ldap_conn(consumer.hostname, consumer.port, rootdn,
                               consumer.admin_pw, starttls(consumer)) as con:
                    if con.compare_s(dn, 'sn', 'gluu'):
                        wlogger.log(
                            taskid,
                            'Failed to remove test data in consumer {}'.format(
                                consumer.hostname), 'error')
            except ldap.NO_SUCH_OBJECT:
                    wlogger.log(
                        taskid,
                        'Test data removed from the consumer: {}'.format(
                            consumer.hostname), 'success')
            except ldap.LDAPError as e:
                wlogger.log(
                    taskid, 'Failed to test consumer: {0}. Error: {1}'.format(
                        consumer.hostname, e), 'error')

    wlogger.log(taskid, 'Replication test Complete.')


def generate_slapd(taskid, server, conffile):
    wlogger.log(taskid, 'Starting preliminary checks')
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
        wlogger.log(taskid, 'Checking if symas-openldap.conf exists', 'fail')
        wlogger.log(taskid, 'Configure OpenLDAP with /opt/gluu/etc/openldap'
                    '/symas-openldap.conf', 'warning')
        return
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
    # 4. Data directories
    wlogger.log(taskid, "Checking for data and schema folders for LDAP")
    conf = open(conffile, 'r')
    for line in conf:
        if re.match('^directory', line):
            folder = line.split()[1]
            if not exists(folder):
                run_command(taskid, 'mkdir -p '+folder)
            else:
                wlogger.log(taskid, folder, 'success')

    # 5. Copy Gluu Schema files
    if not exists('/opt/gluu/schema/openldap'):
        run_command(taskid, 'mkdir -p /opt/gluu/schema/openldap')
    wlogger.log(taskid, "Copying Schema files to server")
    gluu_schemas = os.listdir(os.path.join(app.static_folder, 'schema'))
    for schema in gluu_schemas:
        out = put(os.path.join(app.static_folder, 'schema', schema),
                  "/opt/gluu/schema/openldap/"+schema)
        wlogger.log(taskid, out, "debug")
    # 6. Copy User's custom schema files
    schemas = os.listdir(app.config['SCHEMA_DIR'])
    if len(schemas):
        for schema in schemas:
            out = put(os.path.join(app.config['SCHEMA_DIR'], schema),
                      "/opt/gluu/schema/openldap/"+schema)
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
        wlogger.log(taskid, "Debugging slapd...", "fail")
        run_command(taskid, "service solserver start -d 1")


def chcmd(chdir, command):
    # chroot /chroot_dir /bin/bash -c "<command>"
    return 'chroot /opt/{0} /bin/bash -c "{1}"'.format(chdir, command)


def gen_slapd_gluu(taskid, conffile, version):
    sloc = 'gluu-server-'+version
    # 1. OpenLDAP is installed inside the container
    # 2. symas-openldap.conf file is present inside CE
    # 3. Certificates are generate by setup.py and present
    # 4. Data directories are present in CE installation
    wlogger.log(taskid, "Checking for data and schema folders for LDAP")
    conf = open(conffile, 'r')
    for line in conf:
        if re.match('^directory', line):
            folder = line.split()[1]
            if not exists(os.path.join("/opt/"+sloc, folder)):
                run_command(taskid, chcmd(sloc, 'mkdir -p '+folder))
            else:
                wlogger.log(taskid, folder, 'success')

    # 5. Gluu Schema files are present
    #
    # 6. Copy user's custom schema files
    wlogger.log(taskid, "Copying the custom schemas to the server.")
    schemas = os.listdir(app.config['SCHEMA_DIR'])
    if len(schemas):
        for schema in schemas:
            out = put(os.path.join(app.config['SCHEMA_DIR'], schema),
                      "/opt/"+sloc+"/opt/gluu/schema/openldap/"+schema)
            wlogger.log(taskid, out, "debug")
    # 7. Copy the sladp.conf
    wlogger.log(taskid, "Copying slapd.conf file to remote server")
    out = put(conffile, '/opt/'+sloc+'/opt/symas/etc/openldap/slapd.conf')
    if out.failed:
        wlogger.log(taskid, "Failed to copy the slapd.conf file", "error")
    # 8. Backup openldap.crt to be used in consumers
    wlogger.log(taskid, "Creating backup of openldap.crt")
    out = get("/opt/"+sloc+"/etc/certs/openldap.crt", os.path.join(
        app.config["CERTS_DIR"], "{0}.crt".format(env.host)))
    if out.failed:
        wlogger.log(taskid, "Failed to copy the openldap.crt file", "error")

    wlogger.log(taskid, "Checking status of LDAP server")
    status = run_command(taskid, chcmd(sloc, 'service solserver status'))

    if 'is running' in status:
        wlogger.log(taskid, "Stopping LDAP Server")
        run_command(taskid, chcmd(sloc, 'service solserver stop'))

    with cd('/opt/'+sloc+'/opt/symas/etc/openldap/'):
        wlogger.log(taskid, "Generating slad.d Online Configuration")
        run_command(taskid, 'rm -rf slapd.d')
        run_command(taskid, 'mkdir slapd.d')

    run_command(taskid, chcmd(
        sloc, '/opt/symas/bin/slaptest -f /opt/symas/etc/openldap/slapd.conf '
        ' -F /opt/symas/etc/openldap/slapd.d'))

    wlogger.log(taskid, "Setting ownership of sladp files")
    run_command(taskid, chcmd(sloc, "chown -R ldap:ldap /opt/gluu/data"))
    run_command(taskid,
                chcmd(sloc, "chown -R ldap:ldap /opt/gluu/schema/openldap"))
    run_command(
        taskid,
        chcmd(sloc, "chown -R ldap:ldap /opt/symas/etc/openldap/slapd.d"))

    wlogger.log(taskid, "Starting LDAP server")
    log = run_command(taskid, chcmd(sloc, 'service solserver start'))
    if 'failed' in log:
        wlogger.log(taskid, "Debugging slapd...", "fail")
        run_command(taskid, chcmd(sloc, "service solserver start -d 1"))
        return
    # Restart gluu-server
    wlogger.log(taskid, "Restarting Gluu Server")
    run_command(taskid, 'service '+sloc+' stop')
    run_command(taskid, 'service '+sloc+' start')


def get_olcdb_entry(result):
    for r in result:
        if re.match('^olcDatabase', r[0]):
            if 'olcSuffix' in r[1] and 'o=gluu' in r[1]['olcSuffix']:
                return (r[0], r[1])
    return ('', '')


def copy_certificate(server, certname):
    certfile = os.path.join(app.config["CERTS_DIR"], certname+".crt")
    if server.gluu_server:
        sloc = 'gluu-server-' + server.gluu_version
        put(certfile, "/opt/"+sloc+"/opt/symas/ssl/"+certname+".crt")
    else:
        put(certfile, "/opt/symas/ssl/"+certname+".crt")


def mirror(taskid, s1, s2):
    with settings(warn_only=True):
        execute(copy_certificate, s1, s2.hostname,
                hosts=["root@{}".format(s1.hostname)])

    appconf = AppConfiguration.query.first()
    cnuser = 'cn=admin,cn=config'
    # Prepare the conf for server1
    vals = {'r_id': s2.id, 'phost': s2.hostname, 'pport': s2.port,
            'replication_dn': appconf.replication_dn,
            'replication_pw': appconf.replication_pw,
            'pcert': 'tls_cacert="/opt/symas/ssl/{0}.crt"'.format(s2.hostname),
            'pprotocol': s2.protocol,
            }
    f = open(os.path.join(app.root_path, 'templates', 'slapd', 'mirror.conf'))
    olcSyncrepl = f.read().format(**vals)
    f.close()
    # Find the dn of the o=gluu database in cn=config
    with ldap_conn(s1.hostname, s1.port, cnuser, s1.admin_pw, starttls(s1)) \
            as con:
        result = con.search_s("cn=config", ldap.SCOPE_SUBTREE,
                              "(objectclass=olcMdbConfig)", [])
        dn, dbconfig = get_olcdb_entry(result)
        if not dbconfig:
            wlogger.log(taskid, "Cannot find the Config for o=gluu database.",
                        "error")
            wlogger.log(taskid, result, 'debug')
            return
        if 'olcSyncrepl' in dbconfig:
            modlist = modifyModlist(
                    {'olcSyncrepl': dbconfig['olcSyncrepl']},
                    {'olcSyncrepl': olcSyncrepl}
                    )
        else:
            modlist = [(ldap.MOD_ADD, 'olcSyncrepl', olcSyncrepl)]

        con.modify_s(dn, modlist)

        if 'olcMirrorMode' in dbconfig:
            modlist = modifyModlist(
                    {'olcMirrorMode': dbconfig['olcMirrorMode']},
                    {'olcMirrorMode': 'TRUE'}
                    )
        else:
            modlist = [(ldap.MOD_ADD, 'olcMirrorMode', 'TRUE')]

        con.modify_s(dn, modlist)


@celery.task(bind=True)
def setup_server(self, server_id, conffile):
    server = LDAPServer.query.get(server_id)
    host = "root@{}".format(server.hostname)
    tid = self.request.id
    try:
        with settings(warn_only=True):
            if server.gluu_server:
                execute(gen_slapd_gluu, self.request.id, conffile,
                        server.gluu_version, hosts=[host])
            else:
                execute(generate_slapd, self.request.id, server,
                        conffile, hosts=[host])
    except:
        wlogger.log(tid, "Failed setting up server.", "error")
        t, v = sys.exc_info()[:2]
        wlogger.log(tid, "%s %s" % (t, v), "debug")
        return

    # MirrorMode
    appconf = AppConfiguration.query.first()
    if appconf.topology != 'mirrormode':
        return

    providers = LDAPServer.query.all()
    if len(providers) < 2:
        wlogger.log(tid, "The cluster is configured to work in Mirror Mode. "
                    "Add another provider to setup Mirror Mode.")
        return
    elif len(providers) > 2:
        wlogger.log(tid, "The cluster has more than 2 Providers. It should "
                    "already be working in Mirror Mode. Check Dashboard.")
        return

    wlogger.log(tid, "Setting up MirrorMode between the two providers.")
    s1, s2 = providers
    s1.provider_id = s2.id
    s2.provider_id = s1.id
    db.session.add(s1)
    db.session.add(s2)
    db.session.commit()
    try:
        mirror(self.request.id, s1, s2)
        wlogger.log(tid, "Mirroring {0} to {1}".format(s1.hostname,
                    s2.hostname), "success")
        mirror(self.request.id, s2, s1)
        wlogger.log(tid, "Mirroring {0} to {1}".format(s2.hostname,
                    s1.hostname), "success")
    except:
        wlogger.log(tid, "Mirroring encountered an exception", "fail")
        t, v = sys.exc_info()[:2]
        wlogger.log(tid, "%s %s" % (t, v), "debug")


def modify_oxauth_config(kr, pub_keys=None, openid_jks_pass=""):
    server = LDAPServer.query.filter_by(role="provider").first()

    pub_keys = pub_keys or []
    if not pub_keys:
        return

    with ldap_conn(server.hostname, server.port, "cn=directory manager,o=gluu",
                   server.admin_pw, starttls(server)) as conn:
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
