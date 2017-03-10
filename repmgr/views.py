import random
import os
import redis
import json

from flask import render_template, redirect, url_for, flash, request, jsonify
from celery.result import AsyncResult

from .application import app, db, celery
from .models import LDAPServer, AppConfiguration
from .forms import NewProviderForm, NewConsumerForm
from .tasks import initialize_provider, replicate, setup_server


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
        app.logger.debug(request.form)
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
        provider = None

        server = LDAPServer(host, port, admin_pw, rep_pw, role, starttls,
                            s_id, r_id, provider, cacert, servercert,
                            serverkey)
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
        return render_template("editor.html", config=conf, server=server)

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
                            s_id, r_id, provider_id, cacert, servercert,
                            serverkey)
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
        return render_template("editor.html", config=conf, server=server)

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
    steps = ['conn', 'add', 'recon']
    data = {}
    for step in steps:
        key = 'task:{0}:{1}'.format(task_id, step)
        data[step] = dict([('status', r.get(key)),
                          ('error', r.get(key+':error'))])

    result = AsyncResult(id=task_id, app=celery)
    if result.state == 'SUCCESS':
        for step in steps:
            key = 'task:{0}:{1}'.format(task_id, step)
            r.delete(key)
            r.delete(key+':error')
    return jsonify(data)


@app.route('/fulltest/run')
def test_replication():
    task = replicate.delay()
    return render_template('reptest.html', task=task)


@app.route('/fulltest/<task_id>/status')
def test_status(task_id):
    r = redis.Redis(host='localhost', port=6379, db=0)
    key = 'test:{}'.format(task_id)
    data = r.lrange(key, 0, -1)
    result = AsyncResult(id=task_id, app=celery)
    if result.state == 'SUCCESS':
        r.delete(key)
    return jsonify([json.loads(d) for d in data])


@app.route('/editor/')
def editor():
    return render_template('editor.html')


@app.route('/server/<int:server_id>/setup/', methods=['POST'])
def configure_server(server_id):
    filename = "{}_slapd.conf".format(server_id)
    filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                            'conffiles', filename)
    conf = request.form.get('conf')
    with open(filepath, 'w') as f:
        f.write(conf)

    task_id = setup_server.delay(server_id, filepath)
    return jsonify({'url': url_for('setup_log',
                    server_id=server_id, task_id=task_id)})


@app.route('/server/<int:server_id>/setup/<task_id>')
def setup_log(server_id, task_id):
    r = redis.Redis(host='localhost', port=6379, db=0)
    key = 'task:{}'.format(task_id)
    result = AsyncResult(id=task_id, app=celery)
    data = {'state': result.state, 'log': '\n'.join(r.lrange(key, 0, -1))}
    if result.state == 'SUCCESS' or result.state == 'FAILURE':
        r.delete(key)
    return jsonify(data)
