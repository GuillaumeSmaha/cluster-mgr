import os

import requests
from flask import render_template, redirect, url_for, flash, request, jsonify
from werkzeug.utils import secure_filename
from celery.result import AsyncResult

from .msgcon import get_audit_logs, get_server_logs, \
    get_server_log_item, get_audit_log_item, \
    LogCollection, LogItem
from .application import app, db, celery, wlogger
from .models import LDAPServer, AppConfiguration, KeyRotation, \
    OxauthServer, LoggingServer
from .forms import NewProviderForm, NewConsumerForm, AppConfigForm, \
    KeyRotationForm, SchemaForm, LoggingServerForm, LDIFForm
from .tasks import initialize_provider, replicate, setup_server, \
    rotate_pub_keys
from .utils import ldap_encode
from .utils import encrypt_text
from .utils import generate_random_key
from .utils import generate_random_iv


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    config = AppConfiguration.query.first()
    if len(servers) == 0:
        return render_template('intro.html')

    data = {"provider": 0, "consumer": 0, "topology": config.topology,
            "last_test": config.last_test}
    for server in servers:
        if server.role == 'provider':
            data["provider"] += 1
        elif server.role == 'consumer':
            data["consumer"] += 1

    return render_template('dashboard.html', data=data, servers=servers)


@app.route('/error/<error>/')
def error_page(error=None):
    return render_template('error.html', error=error)


@app.route('/configuration/', methods=['GET', 'POST'])
def app_configuration():
    conf_form = AppConfigForm()
    sch_form = SchemaForm()
    config = AppConfiguration.query.first()
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

    if config and config.replication_dn:
        conf_form.replication_dn.data = config.replication_dn.replace(
            "cn=", "").replace(",o=gluu", "")
        conf_form.replication_pw.data = config.replication_pw
        conf_form.certificate_folder.data = config.certificate_folder

    return render_template('app_config.html', cform=conf_form, sform=sch_form,
                           config=config, schemafiles=schemafiles,
                           next=request.args.get('next'))


@app.route('/cluster/<topology>/')
def setup_cluster(topology):
    config = AppConfiguration.query.first()
    if not config:
        config = AppConfiguration()
    config.topology = topology
    db.session.add(config)
    db.session.commit()

    if not config.replication_dn or not config.replication_pw:
        flash("Replication Manager DN and Password needs to be set before "
              "cluster can be created. Kindly configure now.", "warning")
        return redirect(url_for('app_configuration',
                        next=url_for('setup_cluster', topology=topology)))

    return redirect(url_for('new_server', stype='provider'))


@app.route('/server/new/<stype>/', methods=['GET', 'POST'])
def new_server(stype):
    servers = LDAPServer.query.all()
    config = AppConfiguration.query.first()
    if stype == 'provider':
        form = NewProviderForm()
        if len(servers) == 1 and config.topology == 'delta':
            flash("Only 1 provider can be configured in the \"delta-syncrepl\""
                  " topology. Kindly change the topology and try again!",
                  "danger")
            return redirect(url_for('home'))
        elif len(servers) == 2 and config.topology == 'mirror':
            flash("Only 1 provider can be configured in the \"mirror mode\""
                  " topology. Kindly change the topology and try again!",
                  "danger")
            return redirect(url_for('home'))

    elif stype == 'consumer':
        form = NewConsumerForm()
        form.provider.choices = [
                (p.id, p.hostname) for p in LDAPServer.query.filter_by(
                    role='provider').all()]
        if len(form.provider.choices) == 0:
            return redirect(url_for('error_page', error='no-provider'))

    if form.validate_on_submit():
        s = LDAPServer()
        s.hostname = form.hostname.data
        s.port = form.port.data
        s.role = stype
        s.protocol = form.protocol.data
        s.tls_cacert = form.tls_cacert.data
        s.tls_servercert = form.tls_servercert.data
        s.tls_serverkey = form.tls_serverkey.data
        s.initialized = False
        s.setup = False
        s.admin_pw = form.admin_pw.data
        s.provider_id = None if stype == 'provider' else form.provider.data
        s.gluu_server = form.gluu_server.data
        s.gluu_version = form.gluu_version.data
        db.session.add(s)
        try:
            db.session.commit()
        except:
            flash("Failed to add new server {0}. Probably it is a duplicate."
                  "".format(form.hostname.data), "danger")
            return redirect(url_for('home'))
        return redirect(url_for('setup_ldap_server', server_id=s.id, step=2))

    if stype == 'provider':
        return render_template('new_provider.html', form=form)
    elif stype == 'consumer':
        return render_template('new_consumer.html', form=form)


def generate_conf(server):
    appconfig = AppConfiguration.query.first()
    s = server
    conf = ''
    confile = os.path.join(app.root_path, "templates", "slapd",
                           s.role+".conf")
    with open(confile, 'r') as c:
        conf = c.read()
    vals = {"openldapTLSCACert": "",
            "openldapTLSCert": "",
            "openldapTLSKey": "",
            "encoded_ldap_pw": ldap_encode(s.admin_pw),
            "server_id": s.id,
            "replication_dn": appconfig.replication_dn,
            "openldapSchemaFolder": "/opt/gluu/schema/openldap",
            "BCRYPT": "{BCRYPT}"}
    if s.tls_cacert:
        vals["openldapTLSCACert"] = 'TLSCACertificateFile "%s"' % s.tls_cacert
    if s.tls_servercert:
        vals["openldapTLSCert"] = 'TLSCertificateFile "%s"' % s.tls_servercert
    if s.tls_serverkey:
        vals["openldapTLSKey"] = 'TLSCertificateKeyFile "%s"' % s.tls_serverkey

    if s.role == 'consumer':
        vals["r_id"] = s.provider_id
        vals["phost"] = s.provider.hostname
        vals["pport"] = s.provider.port
        vals["r_pw"] = appconfig.replication_pw
        vals["pprotocol"] = "ldap"
        vals["provider_cert"] = ""
        if s.provider.protocol == "ldaps":
            vals["pprotocol"] = "ldaps"
        if s.provider.protocol != "ldap":
            vals["provider_cert"] = "tls_cacert=\"/opt/symas/ssl/{0}.crt\"".format(
                    s.provider.hostname)

    conf = conf.format(**vals)
    return conf


@app.route('/server/<int:server_id>/setup/<int:step>/', methods=['GET', 'POST'])
def setup_ldap_server(server_id, step):
    s = LDAPServer.query.get(server_id)
    if step == 1:
        return redirect(url_for('home'))
    if s is None:
        flash('Cannot find the server with ID: %s' % server_id, 'warning')
        return redirect(url_for('home'))
    if step == 2:
        if request.method == 'POST':
            conf = request.form['conf']
            filename = os.path.join(app.config['SLAPDCONF_DIR'],
                                    "{0}_slapd.conf".format(server_id))
            with open(filename, 'w') as f:
                f.write(conf)
            return redirect(url_for("setup_ldap_server", server_id=server_id,
                            step=3))
        conf = generate_conf(s)
        return render_template("conf_editor.html", server=s, config=conf)
    elif step == 3:
        appconf = AppConfiguration.query.first()
        provider_count = LDAPServer.query.filter_by(role='provider').count()
        if appconf.topology == 'mirrormode' and provider_count == 1:
            nextpage = 'provider'
        else:
            nextpage = 'dashboard'
        conffile = os.path.join(app.config['SLAPDCONF_DIR'],
                                "{0}_slapd.conf".format(server_id))
        task = setup_server.delay(server_id, conffile)
        head = "Setting up server: "+s.hostname
        return render_template("logger.html", heading=head, server=s,
                               task=task, nextpage=nextpage)


@app.route('/server/<int:server_id>/ldif_upload/', methods=["GET", "POST"])
def ldif_upload(server_id):
    form = LDIFForm()
    if form.validate_on_submit():
        f = form.ldif.data
        filename = "{0}_{1}".format(server_id, 'init.ldif')
        f.save(os.path.join(app.config['LDIF_DIR'], filename))
        return redirect(url_for('initialize', server_id=server_id)+"?ldif=1")
    return render_template('ldif_upload.html', form=form)


@app.route('/server/<int:server_id>/remove/')
def remove_server(server_id):
    s = LDAPServer.query.get(server_id)
    flash('Server %s removed from cluster configuration.' % s.hostname,
          "success")
    db.session.delete(s)
    db.session.commit()
    return redirect(url_for('home'))


@app.route('/initialize/<int:server_id>/')
def initialize(server_id):
    """Initialize function establishes starttls connection, authenticates
    and adds the replicator account to the o=gluu suffix."""
    server = LDAPServer.query.get(server_id)
    use_ldif = bool(request.args.get('ldif', 0))
    if not server:
        return redirect(url_for('error', error='invalid-id-for-init'))
    if server.role != 'provider':
        flash("Intialization is required only for provider. %s is not a "
              "provider. Nothing done." % server.hostname, "warning")
        return redirect(url_for('home'))

    task = initialize_provider.delay(server_id, use_ldif)
    head = "Initializing server"
    return render_template('logger.html', heading=head, server=server,
                           task=task)


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
    head = "Replication Test"
    return render_template('logger.html', heading=head, task=task)


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
