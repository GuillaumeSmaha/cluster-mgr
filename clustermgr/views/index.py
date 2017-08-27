import os

from flask import Blueprint, render_template, redirect, url_for, flash, \
        request, jsonify
from flask import current_app as app
from werkzeug.utils import secure_filename
from celery.result import AsyncResult

from clustermgr.extensions import db, wlogger, celery
from clustermgr.models import LDAPServer, AppConfiguration, KeyRotation, \
    OxauthServer
from clustermgr.forms import AppConfigForm, KeyRotationForm, SchemaForm
from clustermgr.tasks.all import rotate_pub_keys
from clustermgr.core.utils import encrypt_text
from clustermgr.core.utils import generate_random_key
from clustermgr.core.utils import generate_random_iv

index = Blueprint('index', __name__)


@index.route('/')
def home():
    servers = LDAPServer.query.all()
    config = AppConfiguration.query.first()
    if len(servers) == 0:
        return render_template('intro.html')

    data = {"provider": 0, "consumer": 0}
    for server in servers:
        if server.role == 'provider':
            data["provider"] += 1
        elif server.role == 'consumer':
            data["consumer"] += 1

    return render_template('dashboard.html', data=data, servers=servers,
                           conf=config)


@index.route('/configuration/', methods=['GET', 'POST'])
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


@index.route("/key_rotation", methods=["GET", "POST"])
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


@index.route("/api/oxauth_server", methods=["GET", "POST"])
def oxauth_server():
    if request.method == "POST":
        hostname = request.form.get("hostname")
        gluu_server = request.form.get("gluu_server")
        gluu_version = request.form.get("gluu_version")

        if gluu_server == "true":
            gluu_server = True
        else:
            gluu_server = False
            gluu_version = ""

        if not hostname:
            return jsonify({
                "status": 400,
                "message": "Invalid data",
                "params": "hostname can't be empty",
            }), 400

        server = OxauthServer()
        server.hostname = hostname
        server.gluu_server = gluu_server
        server.gluu_version = gluu_version
        db.session.add(server)
        db.session.commit()
        return jsonify({
            "id": server.id,
            "hostname": server.hostname,
            "gluu_server": server.gluu_server,
            "get_version": server.get_version,
        }), 201

    servers = [{
        "id": srv.id,
        "hostname": srv.hostname,
        "version": srv.get_version,
        "gluu_server": srv.gluu_server,
    } for srv in OxauthServer.query]
    return jsonify(servers)


@index.route("/api/oxauth_server/<id>", methods=["POST"])
def delete_oxauth_server(id):
    server = OxauthServer.query.get(id)
    if server:
        db.session.delete(server)
        db.session.commit()
    return jsonify({}), 204


@index.route('/log/<task_id>')
def get_log(task_id):
    msgs = wlogger.get_messages(task_id)
    result = AsyncResult(id=task_id, app=celery)
    if result.state == 'SUCCESS' or result.state == 'FAILED':
        wlogger.clean(task_id)
    log = {'task_id': task_id, 'state': result.state, 'messages': msgs}
    return jsonify(log)
