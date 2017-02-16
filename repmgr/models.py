from .application import db


class LDAPServer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(150))
    port = db.Column(db.Integer)
    role = db.Column(db.String(10))
    starttls = db.Column(db.Boolean)
    server_id = db.Column(db.Integer)
    replication_id = db.Column(db.Integer)

    def __init__(self, hostname, port, role, starttls, s_id, r_id):
        self.hostname = hostname
        self.port = port
        self.role = role
        self.starttls = starttls
        self.server_id = s_id
        self.replication_id = r_id

    def __repr__(self):
        return '<Server %s:%d>' % (self.hostname, self.port)
