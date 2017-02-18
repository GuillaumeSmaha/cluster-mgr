import ldap

from flask import render_template, redirect, url_for, flash, request

from .application import app, db
from .models import LDAPServer, AppConfiguration
from .forms import NewMasterForm


@app.route('/')
def home():
    servers = LDAPServer.query.all()
    return render_template('index.html', servers=servers)


@app.route('/add_master/', methods=['GET', 'POST'])
def add_master():
    form = NewMasterForm()
    if form.validate_on_submit():
        # ensure the connection to the server
        url = "ldap://{}:{}".format(form.hostname.data, form.port.data)
        # TODO remove the following line once SSL Certs location is built
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        con = ldap.initialize(url)
        try:
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
        flash("Sucessfully added %s, master server with ID: %d." %
              (form.hostname.data, form.server_id.data), "success")
        return redirect(url_for('home'))
    return render_template("add_master.html", form=form)


@app.route('/configuration/', methods=['GET', 'POST'])
def app_configuration():
    config = AppConfiguration.query.filter(AppConfiguration.id == 1).first()
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
