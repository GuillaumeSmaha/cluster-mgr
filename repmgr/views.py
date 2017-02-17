from flask import render_template, request, redirect, url_for

from .application import app, db
from .models import LDAPServer
from .forms import NewServerForm, NewMasterForm


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    return render_template('index.html', servers=servers)


@app.route('/add_server/', methods=['GET', 'POST'])
def add_server():
    form = NewServerForm()
    if form.validate_on_submit():
        server = LDAPServer(form.host.data, form.port.data, form.role.data,
                            form.starttls.data,
                            form.server_id.data, form.replication_id.data)
        db.session.add(server)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template("add_server.html", form=form)


@app.route('/add_master/', methods=['GET', 'POST'])
def add_master():
    form = NewMasterForm()
    if form.validate_on_submit():
        server = LDAPServer(form.hostname.data, form.port.data, 'master',
                            form.starttls.data, form.server_id.data,
                            form.replication_id.data, form.manager_dn.data,
                            form.manager_pw.data)
        db.session.add(server)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template("add_master.html", form=form)
