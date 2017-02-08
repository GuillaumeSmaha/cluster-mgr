from .application import db


class LDAPServer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(30))
    hostname = db.Column(db.String(150))
    port = db.Column(db.Integer)

    def __init__(self, hostname, port, ip=None):
        self.hostname = hostname
        self.port = port
        self.ip = ip

    def __repr__(self):
        return '<Server %s:%d>' % (self.hostname, self.port)
