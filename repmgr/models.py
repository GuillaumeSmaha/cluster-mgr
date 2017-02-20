from .application import db


class LDAPServer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(150))
    port = db.Column(db.Integer)
    role = db.Column(db.String(10))
    starttls = db.Column(db.Boolean)
    server_id = db.Column(db.Integer)
    replication_id = db.Column(db.Integer)
    tls_cacert = db.Column(db.Text)
    tls_servercert = db.Column(db.Text)
    tls_serverkey = db.Column(db.Text)
    initialized = db.Column(db.Boolean)
    admin_pw = db.Column(db.String(150))

    def __init__(self, hostname, port, pw, role, starttls, s_id,
                 r_id, cacert=None, servercert=None, serverkey=None):
        self.hostname = hostname
        self.port = port
        self.role = role
        self.admin_pw = pw
        self.starttls = starttls
        self.server_id = s_id
        self.replication_id = r_id
        self.tls_cacert = cacert
        self.tls_servercert = servercert
        self.tls_serverkey = serverkey
        self.initialized = False

    def __repr__(self):
        return '<Server %s:%d>' % (self.hostname, self.port)


class AppConfiguration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    replication_dn = db.Column(db.String(200))
    replication_pw = db.Column(db.String(200))
    certificate_folder = db.Column(db.String(200))

    def __init__(self, replication_dn, replication_pw, cert_folder):
        self.replication_dn = replication_dn
        self.replication_pw = replication_pw
        self.certificate_folder = cert_folder
