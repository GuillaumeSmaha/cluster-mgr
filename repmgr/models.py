from datetime import datetime
from datetime import timedelta

from .application import db

from sqlalchemy.orm import relationship, backref


class LDAPServer(db.Model):
    __tablename__ = "ldap_server"
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(150))
    port = db.Column(db.Integer)
    role = db.Column(db.String(10))
    starttls = db.Column(db.Boolean)
    tls_cacert = db.Column(db.Text)
    tls_servercert = db.Column(db.Text)
    tls_serverkey = db.Column(db.Text)
    initialized = db.Column(db.Boolean)
    admin_pw = db.Column(db.String(150))
    provider_id = db.Column(db.Integer, db.ForeignKey('ldap_server.id'))
    consumers = relationship("LDAPServer", backref=backref(
        'provider', remote_side=[id]))

    def __init__(self, hostname, port, admin_pw, role, starttls, provider=None,
                 cacert=None, servercert=None, serverkey=None):
        self.hostname = hostname
        self.port = port
        self.role = role
        self.admin_pw = admin_pw
        self.starttls = starttls
        self.tls_cacert = cacert
        self.tls_servercert = servercert
        self.tls_serverkey = serverkey
        self.initialized = False
        self.provider_id = provider

    def __repr__(self):
        return '<Server %s:%d>' % (self.hostname, self.port)


class AppConfiguration(db.Model):
    __tablename__ = 'appconfig'
    id = db.Column(db.Integer, primary_key=True)
    replication_dn = db.Column(db.String(200))
    replication_pw = db.Column(db.String(200))
    certificate_folder = db.Column(db.String(200))
    topology = db.Column(db.String(30))


class KeyRotation(db.Model):
    __tablename__ = "keyrotation"

    id = db.Column(db.Integer, primary_key=True)

    # key rotation interval (in days)
    interval = db.Column(db.Integer)

    # timestamp when last rotation occured
    rotated_at = db.Column(db.DateTime(True))

    # rotation type based on available backends (oxeleven or jks)
    type = db.Column(db.String(16))

    oxeleven_url = db.Column(db.String(255))

    # token used for accessing oxEleven
    # note, token is encrypted when we save into database;
    # to get the actual token, we need to decrypt it
    oxeleven_token = db.Column(db.LargeBinary)

    # random key for token encryption
    oxeleven_token_key = db.Column(db.LargeBinary)

    # random iv for token encryption
    oxeleven_token_iv = db.Column(db.LargeBinary)

    # pubkey ID
    oxeleven_kid = db.Column(db.String(255))

    # inum appliance, useful for searching oxAuth config in LDAP
    inum_appliance = db.Column(db.String(255))

    def should_rotate(self):
        # determine whether we need to rotate the key
        if not self.rotated_at:
            return True
        return datetime.utcnow() > self.next_rotation_at

    @property
    def next_rotation_at(self):
        # when will the keys supposed to be rotated
        return self.rotated_at + timedelta(days=self.interval)


class OxauthServer(db.Model):
    __tablename__ = "oxauth_server"

    id = db.Column(db.Integer, primary_key=True)

    # hostname for SSH access
    hostname = db.Column(db.String(255))
