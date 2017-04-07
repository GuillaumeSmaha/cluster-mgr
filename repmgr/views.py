import os

import requests
from flask import render_template, redirect, url_for, flash, request, jsonify,\
    session
from werkzeug.utils import secure_filename
from celery.result import AsyncResult

from .msgcon import get_audit_logs, get_server_logs, \
    get_server_log_item, get_audit_log_item, \
    LogCollection, LogItem
from .application import app, db, celery, wlogger
from .models import LDAPServer, AppConfiguration, KeyRotation, \
    OxauthServer, LoggingServer
from .forms import NewProviderForm, NewConsumerForm, AppConfigForm, \
    NewMirrorModeForm, KeyRotationForm, SchemaForm, LoggingServerForm
from .tasks import initialize_provider, replicate, setup_server, \
    rotate_pub_keys
from .utils import ldap_encode
from .utils import encrypt_text
from .utils import generate_random_key
from .utils import generate_random_iv


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    return render_template('index.html', servers=servers)


@app.route('/error/<error>/')
def error_page(error=None):
    return render_template('error.html', error=error)


@app.route('/configuration/', methods=['GET', 'POST'])
def app_configuration():
    conf_form = AppConfigForm()
    sch_form = SchemaForm()
    config = AppConfiguration.query.get(1)
    schemafiles = os.listdir(app.config['SCHEMA_DIR'])

    if conf_form.update.data and conf_form.validate_on_submit():
        if not config:
            config = AppConfiguration()
        config.replication_dn = "cn={},o=gluu".format(
            conf_form.replication_dn.data)
        config.replication_pw = conf_form.replication_pw.data
        config.certificate_folder = conf_form.certificate_folder.data

        db.session.add(config)
        db.session.commit()
        flash("Gluu Replication Manager application configuration has been "
              "updated.", "success")
        if request.args.get('next'):
            return redirect(request.args.get('next'))

    elif sch_form.upload.data and sch_form.validate_on_submit():
        f = sch_form.schema.data
        filename = secure_filename(f.filename)
        if any(filename in s for s in schemafiles):
            name, extension = os.path.splitext(filename)
            matches = [s for s in schemafiles if name in s]
            filename = name + "_" + str(len(matches)) + extension
        f.save(os.path.join(app.config['SCHEMA_DIR'], filename))
        schemafiles.append(filename)
        flash("Schema: {0} has been uploaded sucessfully.".format(filename),
              "success")

    if config:
        conf_form.replication_dn.data = config.replication_dn.replace(
            "cn=", "").replace(",o=gluu", "")
        conf_form.replication_pw.data = config.replication_pw
        conf_form.certificate_folder.data = config.certificate_folder

    return render_template('app_config.html', cform=conf_form, sform=sch_form,
                           config=config, schemafiles=schemafiles,
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
        s = LDAPServer()
        s.hostname = form.hostname.data
        s.port = form.port.data
        s.role = 'provider'
        s.starttls = form.starttls.data
        s.tls_cacert = form.tls_cacert.data
        s.tls_servercert = form.tls_servercert.data
        s.tls_serverkey = form.tls_serverkey.data
        s.initialized = False
        s.admin_pw = form.admin_pw.data
        s.provider = None
        s.gluu_server = form.gluu_server.data
        s.gluu_version = form.gluu_version.data
        db.session.add(s)
        db.session.commit()

        conf = ''
        confile = os.path.join(app.root_path, "templates", "slapd",
                               "provider.conf")
        with open(confile, 'r') as c:
            conf = c.read()
        conf_values = {"openldapTLSCACert": s.tls_cacert,
                       "openldapTLSCert": s.tls_servercert,
                       "openldapTLSKey": s.tls_serverkey,
                       "encoded_ldap_pw": ldap_encode(s.admin_pw),
                       "mirror_conf": "",
                       "server_id": s.id,
                       "replication_dn": appconfig.replication_dn,
                       "openldapSchemaFolder": "/opt/gluu/schema/openldap",
                       "BCRYPT": "{BCRYPT}"}
        conf = conf.format(**conf_values)
        return render_template("editor.html", config=conf, server=s)

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
        s = LDAPServer()
        s.hostname = form.hostname.data
        s.port = form.port.data
        s.role = "consumer"
        s.starttls = form.starttls.data
        s.tls_cacert = form.tls_cacert.data
        s.tls_servercert = form.tls_servercert.data
        s.tls_serverkey = form.tls_serverkey.data
        s.initialized = False
        s.admin_pw = form.admin_pw.data
        s.provider_id = form.provider.data
        s.gluu_server = False
        s.gluu_version = None

        db.session.add(s)
        db.session.commit()

        conf = ''
        confile = os.path.join(app.root_path, "templates", "slapd",
                               "consumer.conf")
        with open(confile, 'r') as c:
            conf = c.read()

        appconfig = AppConfiguration.query.get(1)
        provider = LDAPServer.query.get(s.provider_id)
        conf_values = {"TLSCACert": s.tls_cacert,
                       "TLSServerCert": s.tls_servercert,
                       "TLSServerKey": s.tls_serverkey, "admin_pw": s.admin_pw,
                       "phost": provider.hostname, "pport": provider.port,
                       "r_id": provider.id, "r_pw": appconfig.replication_pw,
                       "replication_dn": appconfig.replication_dn
                       }
        conf = conf.format(**conf_values)
        return render_template("editor.html", config=conf, server=s)

    return render_template('new_consumer.html', form=form)


@app.route('/new_mirrormode/', methods=['GET', 'POST'])
def new_mirrormode():
    form = NewMirrorModeForm(request.form)
    if form.validate_on_submit():
        # Server 1
        s1 = LDAPServer()
        s1.hostname = form.host1.data
        s1.port = form.port1.data
        s1.role = 'provider'
        s1.starttls = form.tls1.data
        s1.tls_cacert = form.cacert1.data
        s1.tls_servercert = form.servercert1.data
        s1.tls_serverkey = form.serverkey1.data
        s1.admin_pw = form.admin_pw1.data
        s1.provider_id = None
        s1.gluu_server = False

        db.session.add(s1)
        db.session.flush()

        # Server 2
        s2 = LDAPServer()
        s2.hostname = form.host2.data
        s2.port = form.port2.data
        s2.role = 'provider'
        s2.starttls = form.tls2.data
        s2.tls_cacert = form.cacert2.data
        s2.tls_servercert = form.servercert2.data
        s2.tls_serverkey = form.serverkey2.data
        s2.admin_pw = form.admin_pw2.data
        s2.provider_id = s1.id
        s1.gluu_server = False

        db.session.add(s2)
        db.session.flush()

        s1.provider_id = s2.id
        db.session.add(s1)
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

        return render_template("editor.html", config=conf, server=s1,
                               mirror=s2)

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
        app.config['SLAPDCONF_DIR'], "{}_slapd.conf".format(sid1))
    file2 = os.path.join(
        app.config['SLAPDCONF_DIR'], "{}_slapd.conf".format(sid2))

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
    filepath = os.path.join(app.config['SLAPDCONF_DIR'], filename)
    conf = request.form.get('conf')

    with open(filepath, 'w') as f:
        f.write(conf)

    task_id = setup_server.delay(server_id, filepath)
    return jsonify({'url': url_for('get_log', task_id=task_id)})


@app.route("/key_rotation", methods=["GET", "POST"])
def key_rotation():
    kr = KeyRotation.query.first()
    form = KeyRotationForm()
    oxauth_servers = [server for server in OxauthServer.query]

    if request.method == "GET" and kr is not None:
        form.interval.data = kr.interval
        form.type.data = kr.type
        form.oxeleven_url.data = kr.oxeleven_url
        form.inum_appliance.data = kr.inum_appliance

    if form.validate_on_submit():
        if not kr:
            kr = KeyRotation()

        kr.interval = form.interval.data
        kr.type = form.type.data
        kr.oxeleven_url = form.oxeleven_url.data
        kr.inum_appliance = form.inum_appliance.data
        kr.oxeleven_token_key = generate_random_key()
        kr.oxeleven_token_iv = generate_random_iv()
        kr.oxeleven_token = encrypt_text(
            b"{}".format(form.oxeleven_token.data),
            kr.oxeleven_token_key,
            kr.oxeleven_token_iv,
        )
        db.session.add(kr)
        db.session.commit()
        # rotate the keys immediately
        rotate_pub_keys.delay()
        return redirect(url_for("key_rotation"))
    return render_template("key_rotation.html",
                           form=form,
                           rotation=kr,
                           oxauth_servers=oxauth_servers)


@app.route("/api/oxauth_server", methods=["GET", "POST"])
def oxauth_server():
    if request.method == "POST":
        hostname = request.form.get("hostname")
        if not hostname:
            return jsonify({
                "status": 400,
                "message": "Invalid data",
                "params": "hostname can't be empty",
            }), 400

        server = OxauthServer()
        server.hostname = hostname
        db.session.add(server)
        db.session.commit()
        return jsonify({
            "id": server.id,
            "hostname": server.hostname,
        }), 201

    servers = [{
        "id": srv.id,
        "hostname": srv.hostname,
    } for srv in OxauthServer.query]
    return jsonify(servers)


@app.route("/api/oxauth_server/<id>", methods=["POST"])
def delete_oxauth_server(id):
    server = OxauthServer.query.get(id)
    if server:
        db.session.delete(server)
        db.session.commit()
    return jsonify({}), 204


@app.route("/logging_server", methods=["GET", "POST"])
def logging_server():
    log = LoggingServer.query.first()
    form = LoggingServerForm()

    if request.method == "GET" and log is not None:
        form.url.data = log.url

    if form.validate_on_submit():
        if not log:
            log = LoggingServer()
        log.url = form.url.data
        db.session.add(log)
        db.session.commit()
        return redirect("logging_server")
    return render_template("logging_server.html", log=log, form=form)


@app.route("/logging_server/server-log")
def oxauth_server_log():
    err = ""
    logs = None
    server = LoggingServer.query.first()
    page = request.args.get("page", 0)

    if not server:
        err = "Missing logging server configuration."
        return render_template("oxauth_server_log.html", logs=logs, err=err)

    try:
        data, status_code = get_server_logs(server.url, page)
        logs = LogCollection("oxauth-server-logs", data)
        if not logs.has_logs():
            err = "Logs are not available at the moment. Please try again."
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("oxauth_server_log.html", logs=logs, err=err)


@app.route("/logging_server/audit-log")
def oxauth_audit_log():
    err = ""
    logs = None
    server = LoggingServer.query.first()
    page = request.args.get("page", 0)

    if not server:
        err = "Missing logging server configuration."
        return render_template("oxauth_audit_log.html", logs=logs, err=err)

    try:
        data, status_code = get_audit_logs(server.url, page)
        logs = LogCollection("oauth2-audit-logs", data)
        if not logs.has_logs():
            err = "Logs are not available at the moment. Please try again."
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("oxauth_audit_log.html", logs=logs, err=err)


@app.route("/logging_server/audit_log/<int:id>")
def audit_log_item(id):
    err = ""
    log = None
    server = LoggingServer.query.first()

    if not server:
        err = "Missing logging server configuration."
        return render_template("view_audit_log.html", log=log, err=err)

    try:
        data, status_code = get_audit_log_item(server.url, id)
        if not data:
            err = "Log is not available at the momment. Please try again."
        else:
            log = LogItem(data)
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("view_audit_log.html", log=log, err=err)


@app.route("/logging_server/server_log/<int:id>")
def server_log_item(id):
    err = ""
    log = None
    server = LoggingServer.query.first()

    if not server:
        err = "Missing logging server configuration."
        return render_template("view_server_log.html", log=log, err=err)

    try:
        data, status_code = get_server_log_item(server.url, id)
        if not data:
            err = "Log is not available at the momment. Please try again."
        else:
            log = LogItem(data)
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("view_server_log.html", log=log, err=err)
