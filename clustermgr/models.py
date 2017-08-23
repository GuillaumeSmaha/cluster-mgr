from datetime import datetime
from datetime import timedelta

from clustermgr.extensions import db

from sqlalchemy.orm import relationship, backref


class LDAPServer(db.Model):
    __tablename__ = "ldap_server"

    id = db.Column(db.Integer, primary_key=True)

    # hostname of the ldap server
    hostname = db.Column(db.String(150), unique=True)

    # ip address of the server
    ip = db.Column(db.String(45))

    # port in which the LDAP server is  listening
    port = db.Column(db.Integer)

    # role is either provider or consumer
    role = db.Column(db.String(10))

    # LDAP communication protocol ldap, ldaps, starttls
    protocol = db.Column(db.String(10))

    # location of the certificates in the server
    tls_cacert = db.Column(db.Text)
    tls_servercert = db.Column(db.Text)
    tls_serverkey = db.Column(db.Text)

    # whether the replication user has been added to the DIT
    # and the server is setup with replication
    initialized = db.Column(db.Boolean)

    # whether the server has been setup with proper configuration
    setup = db.Column(db.Boolean)

    # rootDN password for the LDAP server
    admin_pw = db.Column(db.String(150))

    # provider for the consumer LDAP server
    provider_id = db.Column(db.Integer, db.ForeignKey('ldap_server.id'))

    # consumers connected to a provider
    consumers = relationship("LDAPServer", backref=backref(
        'provider', remote_side=[id]))

    # is the LDAP server inside the gluu server chroot container
    gluu_server = db.Column(db.Boolean)

    # gluu server version
    gluu_version = db.Column(db.String(10))

    def __repr__(self):
        return '<Server %s:%d>' % (self.hostname, self.port)


class AppConfiguration(db.Model):
    __tablename__ = 'appconfig'

    id = db.Column(db.Integer, primary_key=True)

    # the DN of the replication user
    replication_dn = db.Column(db.String(200))

    # the password for replication user
    replication_pw = db.Column(db.String(200))

    # folder with the certificates for the app to use
    certificate_folder = db.Column(db.String(200))

    # the result of the last replication test
    last_test = db.Column(db.Boolean)


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
    gluu_server = db.Column(db.Boolean(), default=True)
    gluu_version = db.Column(db.String(10), default="3.0.1")

    @property
    def jks_path(self):
        if not self.gluu_server:
            return "/etc/certs/oxauth-keys.jks"
        return "/opt/gluu-server-{}/etc/certs/oxauth-keys.jks".format(self.gluu_version)

    @property
    def get_version(self):
        if not self.gluu_server:
            return ""
        return self.gluu_version


class LoggingServer(db.Model):
    __tablename__ = "logging_server"

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255))

    # # RDBMS backend, must be ``mysql`` or ``postgres``
    # db_backend = db.Column(db.String(16))

    # # RDBMS hostname or IP address
    # db_host = db.Column(db.String(128))

    # # RDBMS port
    # db_port = db.Column(db.Integer)

    # db_user = db.Column(db.String(128))

    # # encrypted password; need to decrypt it before using the value
    # db_password = db.Column(db.String(255))

    # # ActiveMQ hostname or IP address
    # mq_host = db.Column(db.String(128))

    # # ActiveMQ port
    # mq_port = db.Column(db.Integer)

    # mq_user = db.Column(db.String(128))

    # # encrypted password; need to decrypt it before using the value
    # mq_password = db.Column(db.String(255))


class OxelevenKeyID(db.Model):
    __tablename__ = "oxeleven_key_id"

    id = db.Column(db.Integer, primary_key=True)
    kid = db.Column(db.String(255))
