"""A Flask blueprint with the views and the business logic dealing with
the servers managed in the cluster-manager
"""
import os

from flask import Blueprint, render_template, url_for, flash, redirect, \
        request
from flask import current_app as app


from clustermgr.extensions import db
from clustermgr.models import AppConfiguration, LDAPServer
from clustermgr.forms import NewConsumerForm, NewProviderForm, LDIFForm
from clustermgr.core.utils import ldap_encode
from clustermgr.tasks.all import initialize_provider, replicate
from clustermgr.tasks.cluster import setup_server


cluster = Blueprint('cluster', __name__, template_folder='templates')


@cluster.route('/')
def setup_cluster():
    config = AppConfiguration.query.first()
    if not config:
        config = AppConfiguration()
    db.session.add(config)
    db.session.commit()

    if not config.replication_dn or not config.replication_pw:
        flash("Replication Manager DN and Password needs to be set before "
              "cluster can be created. Kindly configure now.", "warning")
        return redirect(url_for('index.app_configuration',
                                next=url_for('cluster.setup_cluster')))

    return redirect(url_for('cluster.new_server', stype='provider'))


@cluster.route('/new/<stype>/', methods=['GET', 'POST'])
def new_server(stype):
    providers = LDAPServer.query.filter_by(role="provider").all()
    if stype == 'provider':
        form = NewProviderForm()
    elif stype == 'consumer':
        form = NewConsumerForm()
        form.provider.choices = [(p.id, p.hostname) for p in providers]
        if len(form.provider.choices) == 0:
            return redirect(url_for('error_page', error='no-provider'))

    if form.validate_on_submit():
        s = LDAPServer()
        s.hostname = form.hostname.data
        s.ip = form.ip.data
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
            return redirect(url_for('index.home'))
        return redirect(url_for('cluster.setup_ldap_server',
                                server_id=s.id, step=2))

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
            cert = "tls_cacert=\"/opt/symas/ssl/{0}.crt\"".format(
                s.provider.hostname)
            vals["provider_cert"] = cert
    conf = conf.format(**vals)
    return conf


@cluster.route('/server/<int:server_id>/setup/<int:step>/',
               methods=['GET', 'POST'])
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
            return redirect(url_for("cluster.setup_ldap_server",
                                    server_id=server_id, step=3))
        conf = generate_conf(s)
        return render_template("conf_editor.html", server=s, config=conf)
    elif step == 3:
        nextpage = 'dashboard'
        conffile = os.path.join(app.config['SLAPDCONF_DIR'],
                                "{0}_slapd.conf".format(server_id))
        task = setup_server.delay(server_id, conffile)
        head = "Setting up server: "+s.hostname
        return render_template("logger.html", heading=head, server=s,
                               task=task, nextpage=nextpage)


@cluster.route('/server/<int:server_id>/ldif_upload/', methods=["GET", "POST"])
def ldif_upload(server_id):
    form = LDIFForm()
    if form.validate_on_submit():
        f = form.ldif.data
        filename = "{0}_{1}".format(server_id, 'init.ldif')
        f.save(os.path.join(app.config['LDIF_DIR'], filename))
        return redirect(url_for('cluster.initialize', server_id=server_id)+"?ldif=1")
    return render_template('ldif_upload.html', form=form)


@cluster.route('/server/<int:server_id>/remove/')
def remove_server(server_id):
    s = LDAPServer.query.get(server_id)
    flash('Server %s removed from cluster configuration.' % s.hostname,
          "success")
    db.session.delete(s)
    db.session.commit()
    return redirect(url_for('index.home'))


@cluster.route('/initialize/<int:server_id>/')
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


@cluster.route('/fulltest/run')
def test_replication():
    task = replicate.delay()
    head = "Replication Test"
    return render_template('logger.html', heading=head, task=task)
