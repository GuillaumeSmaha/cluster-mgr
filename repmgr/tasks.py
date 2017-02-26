import ldap
import redis

from .application import celery, db
from .models import LDAPServer


def log_error_to_redis(r, tid, step, e):
    key = 'task:{0}:{1}'.format(tid, step)
    r.set(key, 'failed')
    if type(e.message) == dict and 'desc' in e.message:
        r.set(key+':error', e.message['desc'])
    else:
        r.set(key+':error', "%s" % e)


@celery.task(bind=True)
def initialize_provider(self, server_id):
    initialized = False
    server = LDAPServer.query.get(server_id)
    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    r = redis.Redis(host='localhost', port=6379, db=0)
    dn = r'cn=replicator,o=gluu'
    replication_user = [
            ('objectclass', [r'person']),
            ('cn', [r'replicator']),
            ('sn', [r'gluu']),
            ('userpassword', [str(server.replication_pw)])
            ]

    # Step 1: Connection
    con = ldap.initialize('ldap://'+server.hostname)
    try:
        con.start_tls_s()
        con.bind_s('cn=directory manager,o=gluu', server.admin_pw)
        r.set('task:{}:conn'.format(self.request.id), 'success')
    except ldap.LDAPError as e:
        log_error_to_redis(r, self.request.id, 'conn', e)

    # Step 2: Add replication user
    try:
        con.add_s(dn, replication_user)
        r.set('task:{}:add'.format(self.request.id), 'success')
    except ldap.LDAPError as e:
        log_error_to_redis(r, self.request.id, 'add', e)
    finally:
        con.unbind()

    # Step 3: Reconnect as replication user
    try:
        con = ldap.initialize('ldap://'+server.hostname)
        con.start_tls_s()
        con.bind_s('cn=replicator,o=gluu', server.replication_pw)
        r.set('task:{}:recon'.format(self.request.id), 'success')
        initialized = True
    except ldap.LDAPError as e:
        log_error_to_redis(r, self.request.id, 'recon', e)
    finally:
        con.unbind()

    if initialized:
        server.initialized = True
        db.session.add(server)
        db.session.commit()
