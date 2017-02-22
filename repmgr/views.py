import ldap
import random
import os

from flask import render_template, redirect, url_for, flash, request, \
        send_from_directory, Response

from .application import app, db
from .models import LDAPServer, AppConfiguration
from .forms import NewMasterForm, NewProviderForm, NewConsumerForm


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    return render_template('index.html', servers=servers)


@app.route('/error/<error>/')
def error_page(error=None):
    return render_template('error.html', error=error)


@app.route('/add_master/', methods=['GET', 'POST'])
def add_master():
    config = AppConfiguration.query.filter(AppConfiguration.id == 1).first()
    form = NewMasterForm()
    if form.validate_on_submit():
        # ensure the connection to the server
        url = "ldap://{}:{}".format(form.hostname.data, form.port.data)
        # TODO remove the following line once SSL Certs location is built
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        try:
            con = ldap.initialize(url)
            if form.starttls.data:
                con.start_tls_s()
            con.bind_s(form.manager_dn.data, form.manager_pw.data)
            con.unbind()
        except ldap.INVALID_CREDENTIALS:
            flash("Cannot add server. Wrong credentials entered.", "danger")
            return render_template("add_master.html", form=form)
        except ldap.LDAPError as e:
            if type(e.message) == dict and 'desc' in e.message:
                flash("Cannot add server. %s" % e.message['desc'], "danger")
            else:
                flash("Cannot add server. %s" % e, "danger")
            return render_template("add_master.html", form=form)

        # Binding sucess - Store the information in the DB
        server = LDAPServer(form.hostname.data, form.port.data, 'master',
                            form.starttls.data, form.server_id.data,
                            form.replication_id.data, form.manager_dn.data,
                            form.manager_pw.data)
        db.session.add(server)
        db.session.commit()
        # TODO
        # Update the server with the following records
        # 1. replication user
        # 2. OLC config for the provider of delta-syncrepl
        rep_user = [
                ('objectclass', ['person']),
                ('cn', ['replicator']),
                ('userpassword', [config.replication_pw])
                ]
        con = ldap.initialize(url)
        if form.starttls.data:
            con.start_tls_s()
        con.bind_s(form.manager_dn.data, form.manager_pw.data)
        con.add_s(config.replication_dn, rep_user)

        flash("Sucessfully added %s, master server with ID: %d." %
              (form.hostname.data, form.server_id.data), "success")
        return redirect(url_for('home'))
    return render_template("add_master.html", form=form)


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
