from flask import render_template, request

from .application import app
from .models import LDAPServer
from .forms import NewServerForm


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    return render_template('index.html', servers=servers)

@app.route('/add_server/', methods=['GET', 'POST'])
def add_server():
    form = NewServerForm()
    if request.method == 'POST':
        pass
    return render_template("add_server.html", form=form)

