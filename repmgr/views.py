from flask import render_template

from .application import app
from .models import LDAPServer


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    return render_template('index.html', servers=servers)
