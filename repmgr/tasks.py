import ldap
import redis

from .application import celery, db
from .models import LDAPServer


@celery.task(bind=True)
def initialize_provider(self, server_id):
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

    con = ldap.initialize('ldap://'+server.hostname)
    try:
        con.start_tls_s()
        con.bind_s('cn=directory manager,o=gluu', server.admin_pw)
        #flash("Replication user added to the LDAP server.", "success")
        r.set('task:{}:conn'.format(self.request.id), 'success')
    except ldap.LDAPError as e:
        if type(e.message) == dict and 'desc' in e.message:
            #flash("Couldn't add cn=replicator user. %s" % e.message['desc'],
            #      "danger")
            r.set('task:{}:conn'.format(self.request.id), 'failed')
        else:
            #flash("Couldn't add cn=replicator user. %s" % e, "danger")
            r.set('task:{}:conn'.format(self.request.id), 'failed')

    try:
        con.add_s(dn, replication_user)
        r.set('task:{}:add'.format(self.request.id), 'success')
    except ldap.LDAPError as e:
        r.set('task:{}:add'.format(self.request.id), 'failed')
    finally:
        con.unbind()

    try:
        con = ldap.initialize('ldap://'+server.hostname)
        con.start_tls_s()
        con.bind_s('cn=replicator,o=gluu', server.replication_pw)
        #flash("Authentication successful for replicator. Consumers can be "
        #      " setup for the provider: %s" % server.hostname, "success")
        r.set('task:{}:recon'.format(self.request.id), 'success')
    except ldap.INVALID_CREDENTIALS:
        r.set('task:{}:recon'.format(self.request.id), 'failed')
        #flash("Couldn't authenticate as replicator. Replication will fail."
        #      "Kindly try again after sometime.", "danger")
    except ldap.LDAPError as e:
        if type(e.message) == dict and 'desc' in e.message:
            #flash("Couldn't authenticate as replicator.%s" % e.message['desc'],
            #      "danger")
            r.set('task:{}:recon'.format(self.request.id), 'failed')
        else:
            r.set('task:{}:recon'.format(self.request.id), 'failed')
            #flash("Couldn't authenticate as replicator. %s" % e, "danger")
    finally:
        con.unbind()

    if r.get('task:{}:recon'.format(self.request.id)) == 'success':
        server.initialized = True
        db.session.add(server)
        db.session.commit()


@celery.task()
def add(x, y):
    return x+y
