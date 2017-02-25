import ldap
import random
import os
import redis

from flask import render_template, redirect, url_for, flash, request, \
        Response, jsonify
from celery.result import AsyncResult

from .application import app, db, celery
from .models import LDAPServer, AppConfiguration
from .forms import NewProviderForm, NewConsumerForm
from .tasks import initialize_provider


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    return render_template('index.html', servers=servers)


@app.route('/error/<error>/')
def error_page(error=None):
    return render_template('error.html', error=error)


@app.route('/configuration/', methods=['GET', 'POST'])
def app_configuration():
    config = AppConfiguration.query.get(1)
    if request.method == 'POST':
        print request.form
        if config:
            config.replication_dn = request.form.get('replication_dn')
            config.replication_pw = request.form.get('replication_pw')
            config.certificate_folder = request.form.get('cert_folder')
        else:
            config = AppConfiguration(request.form.get('replication_dn'),
                                      request.form.get('replication_pw'),
                                      request.form.get('cert_folder'))
            db.session.add(config)
        db.session.commit()
        flash("Gluu Replicaiton Manager application configuration has been "
              "updated.", "success")

    return render_template('app_config.html', config=config)


@app.route('/new_provider/', methods=['GET', 'POST'])
def new_provider():
    form = NewProviderForm()
    if form.validate_on_submit():
        host = form.hostname.data
        port = form.port.data
        role = 'provider'
        starttls = form.starttls.data
        s_id = random.randint(0, 499)
        r_id = random.randint(500, 999)
        cacert = form.tls_cacert.data
        servercert = form.tls_servercert.data
        serverkey = form.tls_serverkey.data
        admin_pw = form.admin_pw.data
        rep_pw = form.replication_pw.data

        server = LDAPServer(host, port, admin_pw, rep_pw, role, starttls,
                            s_id, r_id, cacert, servercert, serverkey)
        db.session.add(server)
        db.session.commit()

        conf = ''
        confile = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "templates", "provider.conf")
        with open(confile, 'r') as c:
            conf = c.read()
        conf_values = {"TLSCACert": cacert, "TLSServerCert": servercert,
                       "TLSServerKey": serverkey, "admin_pw": admin_pw}
        conf = conf.format(**conf_values)
        return Response(conf, mimetype="text/plain",
                        headers={"Content-disposition":
                                 "attachment; filename=slapd.conf"})

    return render_template('new_provider.html', form=form)


@app.route('/new_consumer/', methods=['GET', 'POST'])
def new_consumer():
    form = NewConsumerForm()
    form.provider.choices = [(p.id, p.hostname)
                             for p in LDAPServer.query.filter_by(
                                 role='provider').all()]
    if len(form.provider.choices) == 0:
        return redirect(url_for('error_page', error='no-provider'))

    if form.validate_on_submit():
        host = form.hostname.data
        port = form.port.data
        role = "consumer"
        starttls = form.starttls.data
        s_id = random.randint(0, 499)
        r_id = random.randint(500, 999)
        cacert = form.tls_cacert.data
        servercert = form.tls_servercert.data
        serverkey = form.tls_serverkey.data
        provider_id = form.provider.data
        admin_pw = form.admin_pw.data

        server = LDAPServer(host, port, admin_pw, '', role, starttls,
                            s_id, r_id, cacert, servercert, serverkey)
        db.session.add(server)
        db.session.commit()

        provider = LDAPServer.query.get(provider_id)
        conf = ''
        confile = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "templates", "consumer.conf")
        with open(confile, 'r') as c:
            conf = c.read()
        conf_values = {"TLSCACert": cacert, "TLSServerCert": servercert,
                       "TLSServerKey": serverkey, "admin_pw": admin_pw,
                       "r_id": r_id, "phost": provider.hostname,
                       "pport": provider.port, "r_pw": provider.replication_pw}
        conf = conf.format(**conf_values)
        return Response(conf, mimetype="text/plain",
                        headers={"Content-disposition":
                                 "attachment; filename=slapd.conf"})

    return render_template('new_consumer.html', form=form)


@app.route('/initialize/<int:server_id>/')
def initialize(server_id):
    """Initialize function establishes starttls connection, authenticates
    and adds the replicator account to the o=gluu suffix."""
    server = LDAPServer.query.get(server_id)
    if not server:
        return redirect(url_for('error', error='invalid-id-for-init'))
    if server.role != 'provider':
        flash("Intialization is required only for provider. %s is not a "
              "provider. Nothing done." % server.hostname, "warning")
        return redirect(url_for('home'))

    task = initialize_provider.delay(server_id)
    return render_template('initialize.html', server=server, task=task)


@app.route('/task/<task_id>')
def task_status(task_id):
    r = redis.Redis(host='localhost', port=6379, db=0)
    s1 = r.get('task:{}:conn'.format(task_id))
    s2 = r.get('task:{}:add'.format(task_id))
    s3 = r.get('task:{}:recon'.format(task_id))
    result = AsyncResult(id=task_id, app=celery)
    if result.state == 'SUCCESSFUL':
        r.delete('task:{}:conn'.format(task_id))
        r.delete('task:{}:add'.format(task_id))
        r.delete('task:{}:recon'.format(task_id))
    return jsonify({'conn': s1, 'add': s2, 'recon': s3})
