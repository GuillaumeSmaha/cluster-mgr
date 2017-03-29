import os

from flask import render_template, redirect, url_for, flash, request, jsonify,\
    session
from celery.result import AsyncResult

from .application import app, db, celery, wlogger
from .models import LDAPServer, AppConfiguration, KeyRotation
from .forms import NewProviderForm, NewConsumerForm, AppConfigForm, \
    NewMirrorModeForm, KeyRotationForm
from .tasks import initialize_provider, replicate, setup_server
from .utils import ldap_encode


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
    appconfig = AppConfiguration.query.first()
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
        confile = os.path.join(app.root_path, "templates", "slapd",
                               "provider.conf")
        with open(confile, 'r') as c:
            conf = c.read()
        conf_values = {"openldapTLSCACert": cacert,
                       "openldapTLSCert": servercert,
                       "openldapTLSKey": serverkey,
                       "encoded_ldap_pw": ldap_encode(admin_pw),
                       "mirror_conf": "",
                       "server_id": server.id,
                       "replication_dn": appconfig.replication_dn,
                       "openldapSchemaFolder": "/opt/gluu/schema/openldap",
                       "BCRYPT": "{BCRYPT}"}
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
        confile = os.path.join(app.root_path, "templates", "slapd",
                               "consumer.conf")
        with open(confile, 'r') as c:
            conf = c.read()

        appconfig = AppConfiguration.query.get(1)
        conf_values = {"TLSCACert": cacert, "TLSServerCert": servercert,
                       "TLSServerKey": serverkey, "admin_pw": admin_pw,
                       "phost": provider.hostname, "pport": provider.port,
                       "r_id": provider.id, "r_pw": appconfig.replication_pw,
                       "replication_dn": appconfig.replication_dn
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
                'pport': s2.port, 'r_pw': appconfig.replication_pw,
                'replication_dn': appconfig.replication_dn}
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

    url1 = url_for('get_log', task_id=task1)
    url2 = url_for('get_log', task_id=task2)

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


@app.route('/log/<task_id>')
def get_log(task_id):
    msgs = wlogger.get_messages(task_id)
    result = AsyncResult(id=task_id, app=celery)
    if result.state == 'SUCCESS' or result.state == 'FAILED':
        wlogger.clean(task_id)
    log = {'task_id': task_id, 'state': result.state, 'messages': msgs}
    return jsonify(log)


@app.route('/fulltest/run')
def test_replication():
    task = replicate.delay()
    return render_template('initialize.html', task=task)


@app.route('/server/<int:server_id>/setup/', methods=['POST'])
def configure_server(server_id):
    filename = "{}_slapd.conf".format(server_id)
    filepath = os.path.join(app.root_path, "conffiles", filename)
    conf = request.form.get('conf')

    with open(filepath, 'w') as f:
        f.write(conf)

    task_id = setup_server.delay(server_id, filepath)
    return jsonify({'url': url_for('get_log', task_id=task_id)})


@app.route("/key_rotation", methods=["GET", "POST"])
def key_rotation():
    rotation = KeyRotation.query.first()
    form = KeyRotationForm()

    if request.method == "GET" and rotation is not None:
        form.interval.data = rotation.interval
        form.type.data = rotation.type
        form.oxeleven_url.data = rotation.oxeleven_url

    if form.validate_on_submit():
        if not rotation:
            rotation = KeyRotation()

        rotation.interval = form.interval.data
        rotation.type = form.type.data
        rotation.oxeleven_url = form.oxeleven_url.data
        rotation.static_token = form.static_token.data
        db.session.add(rotation)
        db.session.commit()
        return redirect(url_for("key_rotation"))
    return render_template("key_rotation.html", form=form, rotation=rotation)
