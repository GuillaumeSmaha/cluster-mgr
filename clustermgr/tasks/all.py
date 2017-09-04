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
from flask import current_app as app

from clustermgr.extensions import celery, db, wlogger
from clustermgr.models import LDAPServer, AppConfiguration, KeyRotation, \
        OxauthServer, OxelevenKeyID
from clustermgr.core.ldaplib import ldap_conn, search_from_ldap
from clustermgr.core.utils import decrypt_text, random_chars
from clustermgr.core.ox11 import generate_key, delete_key
from clustermgr.core.keygen import generate_jks

ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)


class FabricException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

env.abort_exception = FabricException


def starttls(server):
    return server.protocol == 'starttls'


def run_command(taskid, command):
    outlog = StringIO.StringIO()
    errlog = StringIO.StringIO()

    wlogger.log(taskid, command, "debug")
    output = run(command, stdout=outlog, stderr=errlog, timeout=10)
    if outlog.getvalue():
        wlogger.log(taskid, outlog.getvalue(), "debug")
    if errlog.getvalue():
        wlogger.log(taskid, errlog.getvalue(), "error")

    return output


def import_ldif(taskid, ldiffile, server):
    wlogger.log(taskid, "Copying {0} to /tmp/init.ldif".format(ldiffile),
                "debug")
    if server.gluu_server:
        sloc = "gluu-server-"+server.gluu_version
        put(ldiffile, '/opt/'+sloc+'/tmp/init.ldif')
        run_command(taskid, chcmd(sloc, 'service solserver stop'))
        run_command(taskid, chcmd(sloc, '/opt/symas/bin/slapadd -b o=gluu -l /tmp/init.ldif'))
        run_command(taskid, chcmd(sloc, 'service solserver start'))
        run_command(taskid, 'rm /opt/'+sloc+'/tmp/init.ldif')
    else:
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
            execute(import_ldif, self.request.id, ldiffile, s,
                    hosts=[host])

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
            print "Failed to add replication user", sys.exc_info()[2]
            return
    # Step 2: Reconnect as replication user
    try:
        con = ldap.initialize('ldap://{}:{}'.format(s.hostname, s.port))
        if s.protocol == 'starttls':
            con.start_tls_s()
        con.bind_s(repdn, appconfig.replication_pw)
        wlogger.log(taskid, "Authenticating as the Replication DN.", "success")
        initialized = True
    except ldap.SERVER_DOWN:
        con = ldap.initialize('ldaps://{}:{}'.format(s.hostname, s.port))
        con.bind_s(repdn, appconfig.replication_pw)
        wlogger.log(taskid, "Authenticating as the Replication DN.", "success")
        initialized = True
    except ldap.LDAPError as e:
        wlogger.log(taskid, "%s" % e, 'error')
    finally:
        con.unbind()

    if initialized:
        s.initialized = True
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
    test_result = True

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
            v = sys.exc_info()[1]
            wlogger.log(taskid, str(v), "debug")
            test_result = test_result and False

        consumers = provider.consumers
        wlogger.log(taskid,
                    'Listing consumers of provider %s' % provider.hostname)
        # Check the consumers
        for consumer in consumers:
            wlogger.log(taskid, 'Verifying data in consumers: {} of {}'.format(
                consumers.index(consumer)+1, len(consumers)))
            try:
                with ldap_conn(consumer.hostname, consumer.port, rootdn,
                               consumer.admin_pw, starttls(consumer)) as con:
                    if con.compare_s(dn, 'sn', 'gluu'):
                        wlogger.log(
                            taskid,
                            'Test data is replicated and available', 'success')
            except ldap.NO_SUCH_OBJECT:
                wlogger.log(taskid, 'Test data is NOT replicated.', 'error')
                test_result = test_result and False
            except ldap.LDAPError as e:
                wlogger.log(taskid, 'Failed to connect to {0}. {1}'.format(
                                    consumer.hostname, e), 'error')
                test_result = test_result and False

        # delete the entry from the provider
        try:
            with ldap_conn(provider.hostname, provider.port, rootdn,
                           provider.admin_pw, starttls(provider)) as con:
                con.delete_s(dn)
                if con.compare_s(dn, 'sn', 'gluu'):
                    wlogger.log(taskid, 'Delete operation failed. Data exists',
                                'error')
                    test_result = test_result and False
        except ldap.NO_SUCH_OBJECT:
            wlogger.log(taskid, 'Deleting test data from provider: {}'.format(
                provider.hostname), 'success')
        except:
            v = sys.exc_info()[1]
            wlogger.log(taskid, str(v), "debug")
            test_result = test_result and False

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
                        test_result = test_result and False
            except ldap.NO_SUCH_OBJECT:
                    wlogger.log(
                        taskid,
                        'Test data removed from the consumer: {}'.format(
                            consumer.hostname), 'success')
            except ldap.LDAPError as e:
                wlogger.log(
                    taskid, 'Failed to test consumer: {0}. Error: {1}'.format(
                        consumer.hostname, e), 'error')
                test_result = test_result and False

    wlogger.log(taskid, 'Replication test Complete.')
    appconf = AppConfiguration.query.first()
    appconf.last_test = test_result
    db.session.commit()

    return test_result


def chcmd(chdir, command):
    # chroot /chroot_dir /bin/bash -c "<command>"
    return 'chroot /opt/{0} /bin/bash -c "{1}"'.format(chdir, command)


def copy_certificate(server, certname):
    certfile = os.path.join(app.config["CERTS_DIR"], certname+".crt")
    if server.gluu_server:
        sloc = 'gluu-server-' + server.gluu_version
        put(certfile, "/opt/"+sloc+"/opt/symas/ssl/"+certname+".crt")
    else:
        put(certfile, "/opt/symas/ssl/"+certname+".crt")


@celery.task(bind=True)
def setup_server(self, server_id, conffile):
    server = LDAPServer.query.get(server_id)
    host = "root@{}".format(server.hostname)
    tid = self.request.id

    # For consumers with providers using SSL copy their certificates
    if server.role == 'consumer' and server.provider.protocol != 'ldap':
        with settings(warn_only=True):
            execute(copy_certificate, server, server.provider.hostname,
                    hosts=[host])
    # TODO find where this copy certificate routine should be injected in
    # cluster.py

    # Everything is done. Set the flag to based on the messages
    msgs = wlogger.get_messages(tid)
    setup_success = True
    for msg in msgs:
        setup_success = setup_success and msg['level'] != 'error'
    server.setup = setup_success
    db.session.commit()


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

        try:
            # delete old keys first
            print "deleting old keys"
            for key_id in OxelevenKeyID.query:
                status_code, out = delete_key(kr.oxeleven_url, key_id.kid, token)
                if status_code == 200 and out["deleted"]:
                    db.session.delete(key_id)
                    db.session.commit()
                elif status_code == 401:
                    print "insufficient access to call oxEleven API"

            # obtain new keys
            print "obtaining new keys"
            for algo in ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]:
                status_code, out = generate_key(kr.oxeleven_url, algo, token=token)
                if status_code == 200:
                    key_id = OxelevenKeyID()
                    key_id.kid = out["kid"]
                    db.session.add(key_id)
                    db.session.commit()
                    pub_keys.append(out)
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
            def _copy_jks(path, hostname, dest_path):
                out = put(path, dest_path)
                if out.failed:
                    print "unable to copy JKS file to " \
                        "oxAuth server {}".format(hostname)
                else:
                    print "JKS file has been copied " \
                        "to {}".format(hostname)

            for server in OxauthServer.query:
                host = "root@{}".format(server.hostname)
                with settings(warn_only=True):
                    execute(_copy_jks, jks_path, server.hostname,
                            server.jks_path, hosts=[host])


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
