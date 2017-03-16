import os
import redis
import json

from flask import render_template, redirect, url_for, flash, request, jsonify,\
        session
from celery.result import AsyncResult

from .application import app, db, celery
from .models import LDAPServer, AppConfiguration
from .forms import NewProviderForm, NewConsumerForm, AppConfigForm, \
        NewMirrorModeForm
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
    form = AppConfigForm()
    config = AppConfiguration.query.get(1)
    if request.method == 'GET' and config:
        form.replication_dn.data = config.replication_dn.replace(
                "cn=", "").replace(",o=gluu", "") if config.replication_dn \
                        else ""
        form.replication_pw.data = config.replication_pw
        form.certificate_folder.data = config.certificate_folder
    if form.validate_on_submit():
        if not config:
            config = AppConfiguration()
        config.replication_dn = "cn={},o=gluu".format(form.replication_dn.data)
        config.replication_pw = form.replication_pw.data
        config.certificate_folder = form.certificate_folder.data

        db.session.add(config)
        db.session.commit()
        flash("Gluu Replication Manager application configuration has been "
              "updated.", "success")
        if request.args.get('next'):
            return redirect(request.args.get('next'))

    return render_template('app_config.html', form=form, config=config,
                           next=request.args.get('next'))


@app.route('/cluster/<topology>/')
def setup_cluster(topology):
    session['topology'] = topology
    config = AppConfiguration.query.get(1)
    if not config:
        config = AppConfiguration()
        config.topology = topology
        db.session.add(config)
        db.session.commit()

    if not config or not config.replication_dn or not config.replication_pw:
        flash("Replication Manager DN and Password needs to be set before "
              "cluster can be created. Kindly configure now.", "warning")
        return redirect(url_for('app_configuration',
                        next=url_for('setup_cluster', topology=topology)))

    if topology == 'delta':
        flash('Configure a provider to begin managing the cluster.', 'info')
        return redirect(url_for('new_provider'))
    elif topology == 'mirrormode':
        return redirect(url_for('new_mirrormode'))
    else:
        return redirect(url_for('error_page', error='unknown-topology'))


@app.route('/new_provider/', methods=['GET', 'POST'])
def new_provider():
    form = NewProviderForm(request.form)
    if form.validate_on_submit():
        host = form.hostname.data
        port = form.port.data
        role = 'provider'
        starttls = form.starttls.data
        cacert = form.tls_cacert.data
        servercert = form.tls_servercert.data
        serverkey = form.tls_serverkey.data
        admin_pw = form.admin_pw.data
        provider = None

        server = LDAPServer(host, port, admin_pw, role, starttls,
                            provider, cacert, servercert, serverkey)
        db.session.add(server)
        db.session.commit()

        conf = ''
        confile = os.path.join(app.root_path, "templates", "slapd", "provider.conf")
        with open(confile, 'r') as c:
            conf = c.read()
        conf_values = {"TLSCACert": cacert, "TLSServerCert": servercert,
                       "TLSServerKey": serverkey, "admin_pw": admin_pw,
                       "mirror_conf": "", "server_id": server.id}
        conf = conf.format(**conf_values)
        return render_template("editor.html", config=conf, server=server)

    return render_template('new_provider.html', form=form)


@app.route('/new_consumer/', methods=['GET', 'POST'])
def new_consumer():
    form = NewConsumerForm(request.form)
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
        cacert = form.tls_cacert.data
        servercert = form.tls_servercert.data
        serverkey = form.tls_serverkey.data
        provider_id = form.provider.data
        admin_pw = form.admin_pw.data
        provider = LDAPServer.query.get(provider_id)

        server = LDAPServer(host, port, admin_pw, role, starttls,
                            provider_id, cacert, servercert, serverkey)
        db.session.add(server)
        db.session.commit()

        conf = ''
        confile = os.path.join(app.root_path, "templates", "slapd", "consumer.conf")
        with open(confile, 'r') as c:
            conf = c.read()

        appconfig = AppConfiguration.query.get(1)
        conf_values = {"TLSCACert": cacert, "TLSServerCert": servercert,
                       "TLSServerKey": serverkey, "admin_pw": admin_pw,
                       "r_id": provider.id, "phost": provider.hostname,
                       "pport": provider.port, "r_pw": appconfig.replication_pw
                       }
        conf = conf.format(**conf_values)
        return render_template("editor.html", config=conf, server=server)

    return render_template('new_consumer.html', form=form)


@app.route('/new_mirrormode/', methods=['GET', 'POST'])
def new_mirrormode():
    form = NewMirrorModeForm(request.form)
    if form.validate_on_submit():
        # Server 1
        host = form.host1.data
        port = form.port1.data
        role = 'provider'
        starttls = form.tls1.data
        cacert = form.cacert1.data
        servercert = form.servercert1.data
        serverkey = form.serverkey1.data
        admin_pw = form.admin_pw1.data
        provider = None

        server1 = LDAPServer(host, port, admin_pw, role, starttls,
                             provider, cacert, servercert, serverkey)
        db.session.add(server1)
        db.session.flush()

        # Server 2
        host = form.host2.data
        port = form.port2.data
        role = 'provider'
        starttls = form.tls2.data
        cacert = form.cacert2.data
        servercert = form.servercert2.data
        serverkey = form.serverkey2.data
        admin_pw = form.admin_pw2.data
        provider = server1.id

        server2 = LDAPServer(host, port, admin_pw, role, starttls,
                             provider, cacert, servercert, serverkey)
        db.session.add(server2)
        db.session.flush()

        server1.provider_id = server2.id
        db.session.add(server1)
        db.session.commit()

        conf = ''
        confile = os.path.join(
                app.root_path, "templates", "slapd", "provider.conf")
        mirrorfile = os.path.join(
                app.root_path, "templates", "slapd", "mirror.conf")
        with open(confile, 'r') as c:
            conf = c.read()
        with open(mirrorfile, 'r') as m:
            mirror = m.read()
        conf = conf.replace('{mirror_conf}', mirror)

        return render_template("editor.html", config=conf, server=server1,
                               mirror=server2)

    return render_template('new_mirror_providers.html', form=form)


def generate_mirror_conf(filename, template, s1, s2):
    appconfig = AppConfiguration.query.get(1)
    with open(filename, 'w') as f:
        vals = {'TLSCACert': s1.tls_cacert, 'TLSServerCert': s1.tls_servercert,
                'TLSServerKey': s1.tls_serverkey, 'admin_pw': s1.admin_pw,
                'server_id': s1.id, 'r_id': s2.id, 'phost': s2.hostname,
                'pport': s2.port, 'r_pw': appconfig.replication_pw}
        conf = template.format(**vals)
        f.write(conf)


@app.route('/mirror/<int:sid1>/<int:sid2>/', methods=['POST'])
def mirror(sid1, sid2):
    s1 = LDAPServer.query.get(sid1)
    s2 = LDAPServer.query.get(sid2)

    file1 = os.path.join(
            app.root_path, "conffiles", "{}_slapd.conf".format(sid1))
    file2 = os.path.join(
            app.root_path, "conffiles", "{}_slapd.conf".format(sid2))

    template = request.form.get('conf')
    generate_mirror_conf(file1, template, s1, s2)
    generate_mirror_conf(file2, template, s2, s1)

    task1 = setup_server.delay(sid1, file1)
    task2 = setup_server.delay(sid2, file2)

    url1 = url_for('setup_log', server_id=sid1, task_id=task1)
    url2 = url_for('setup_log', server_id=sid2, task_id=task2)

    return jsonify({'url1': url1, 'url2': url2})


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


@app.route('/server/<int:server_id>/setup/', methods=['POST'])
def configure_server(server_id):
    filename = "{}_slapd.conf".format(server_id)
    filepath = os.path.join(app.root_path, "conffiles", filename)
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
