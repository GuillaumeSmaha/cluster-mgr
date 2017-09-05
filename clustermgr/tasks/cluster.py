import re
import os

from flask import current_app as app

from clustermgr.models import LDAPServer
from clustermgr.extensions import celery, wlogger, db
from clustermgr.core.remote import RemoteClient


def run_command(tid, c, command, container=None):
    """Shorthand for RemoteClient.run(). This function automatically logs
    the commands output at appropriate levels to the WebLogger to be shared
    in the web frontend.

    Args:
        tid (string): task id of the task to store the log
        c (:object:`clustermgr.core.remote.RemoteClient`): client to be used
            for the SSH communication
        command (string): the command to be run on the remote server
        container (string, optional): location where the Gluu Server container
            is installed. For standalone LDAP servers this is not necessary.

    Returns:
        the output of the command or the err thrown by the command as a string
    """
    if container:
        command = 'chroot {0} /bin/bash -c "{1}"'.format(container,
                                                         command)

    wlogger.log(tid, command, "debug")
    cin, cout, cerr = c.run(command)
    output = ''
    if cout:
        wlogger.log(tid, cout, "debug")
        output = cout
    if cerr:
        # For some reason slaptest decides to send success message as err, so
        if 'config file testing succeeded' in cerr:
            wlogger.log(tid, cerr, "success")
        else:
            wlogger.log(tid, cerr, "error")
        output += "\n" + cerr
    return output


def upload_file(tid, c, local, remote):
    """Shorthand for RemoteClient.upload(). This function automatically handles
    the logging of events to the WebLogger

    Args:
        tid (string): id of the task running the command
        c (:object:`clustermgr.core.remote.RemoteClient`): client to be used
            for the SSH communication
        local (string): local location of the file to upload
        remote (string): location of the file in remote server
    """
    out = c.upload(local, remote)
    wlogger.log(tid, out, 'error' if 'Error' in out else 'success')


def download_file(tid, c, remote, local):
    """Shorthand for RemoteClient.download(). This function automatically handles
    the logging of events to the WebLogger

    Args:
        tid (string): id of the task running the command
        c (:object:`clustermgr.core.remote.RemoteClient`): client to be used
            for the SSH communication
        remote (string): location of the file in remote server
        local (string): local location of the file to upload
    """
    out = c.download(remote, local)
    wlogger.log(tid, out, 'error' if 'Error' in out else 'success')


@celery.task(bind=True)
def setup_server(self, server_id, conffile):
    """This Task sets up a standalone server with only OpenLDAP installed as
    per the request.

    As the task proceeds the various status are logged to the WebLogger under
    the uniqueID of the task. This lets the web interface to poll for the
    near-realtime updates.

    Args:
        server_id (int): the primary key of the LDAPServer object
        conffile (string): complete path of the slapd.conf generated via webui
    """
    server = LDAPServer.query.get(server_id)
    tid = self.request.id

    wlogger.log(tid, "Connecting to the server %s" % server.hostname)
    c = RemoteClient(server.hostname)
    try:
        c.startup()
    except Exception as e:
        wlogger.log(tid, "Cannot establish SSH connection {0}".format(e),
                    "error")

    wlogger.log(tid, "Retrying with the IP address")
    c = RemoteClient(server.ip)
    try:
        c.startup()
    except Exception as e:
        wlogger.log(tid, "Cannot establish SSH connection {0}".format(e),
                    "error")
        wlogger.log(tid, "Ending server setup process.", "error")
        return False

    wlogger.log(tid, 'Starting premilinary checks')
    # 1. Check OpenLDAP is installed
    if c.exists('/opt/symas/bin/slaptest'):
        wlogger.log(tid, 'Checking if OpenLDAP is installed', 'success')
    else:
        wlogger.log(tid, 'Cheking if OpenLDAP is installed', 'fail')
        wlogger.log(tid, 'Kindly install OpenLDAP on the server and refresh'
                    ' this page to try setup again.')
        return

    # 2. symas-openldap.conf file exists
    if c.exists('/opt/symas/etc/openldap/symas-openldap.conf'):
        wlogger.log(tid, 'Checking symas-openldap.conf exists', 'success')
    else:
        wlogger.log(tid, 'Checking if symas-openldap.conf exists', 'fail')
        wlogger.log(tid, 'Configure OpenLDAP with /opt/gluu/etc/openldap'
                    '/symas-openldap.conf', 'warning')
        return

    # 3. Certificates
    if server.tls_cacert:
        if c.exists(server.tls_cacert):
            wlogger.log(tid, 'Checking TLS CA Certificate', 'success')
        else:
            wlogger.log(tid, 'Checking TLS CA Certificate', 'fail')
    if server.tls_servercert:
        if c.exists(server.tls_servercert):
            wlogger.log(tid, 'Checking TLS Server Certificate', 'success')
        else:
            wlogger.log(tid, 'Checking TLS Server Certificate', 'fail')
    if server.tls_serverkey:
        if c.exists(server.tls_serverkey):
            wlogger.log(tid, 'Checking TLS Server Key', 'success')
        else:
            wlogger.log(tid, 'Checking TLS Server Key', 'fail')

    # 4. Data directories
    wlogger.log(tid, "Checking for data and schema folders for LDAP")
    conf = open(conffile, 'r')
    for line in conf:
        if re.match('^directory', line):
            folder = line.split()[1]
            if not c.exists(folder):
                run_command(tid, c, 'mkdir -p '+folder)
            else:
                wlogger.log(tid, folder, 'success')

    # 5. Copy Gluu Schema files
    wlogger.log(tid, "Copying Schema files to server")
    if not c.exists('/opt/gluu/schema/openldap'):
        run_command(tid, c, 'mkdir -p /opt/gluu/schema/openldap')
    gluu_schemas = os.listdir(os.path.join(app.static_folder, 'schema'))
    for schema in gluu_schemas:
        upload_file(tid, c, os.path.join(app.static_folder, 'schema', schema),
                    "/opt/gluu/schema/openldap/"+schema)
    # 6. Copy User's custom schema files
    schemas = os.listdir(app.config['SCHEMA_DIR'])
    for schema in schemas:
        upload_file(tid, c, os.path.join(app.config['SCHEMA_DIR'], schema),
                    "/opt/gluu/schema/openldap/"+schema)

    # 7. Setup slapd.conf
    wlogger.log(tid, "Copying slapd.conf file to remote server")
    upload_file(tid, c, conffile, '/opt/symas/etc/openldap/slapd.conf')

    wlogger.log(tid, "Restarting LDAP server to validate slapd.conf")
    # IMPORTANT:
    # Restart allows the server to create missing mdb files for accesslog so
    # slapd.conf -> slapd.d conversion runs without error
    run_command(tid, c, 'service solserver restart')

    # 8. Generate OLC slapd.d
    wlogger.log(tid, "Migrating from slapd.conf to slapd.d OnlineConfig (OLC)")
    run_command(tid, c, 'service solserver stop')
    run_command(tid, c, 'rm -rf /opt/symas/etc/openldap/slapd.d')
    run_command(tid, c, 'mkdir -p /opt/symas/etc/openldap/slapd.d')
    run_command(tid, c,
                '/opt/symas/bin/slaptest -f /opt/symas/etc/openldap/slapd.conf'
                ' -F /opt/symas/etc/openldap/slapd.d')

    # 9. Restart the solserver with the new configuration
    wlogger.log(tid, "Starting LDAP server with OLC configuraion. Any future"
                "changes to slapd.conf will have NO effect on the LDAP server")
    log = run_command(tid, c, 'service solserver start')
    if 'failed' in log:
        wlogger.log(tid, "OpenLDAP server failed to start.", "error")
        wlogger.log(tid, "Debugging slapd...", "info")
        run_command(tid, "service solserver start -d 1")

    # Everything is done. Set the flag to based on the messages
    msgs = wlogger.get_messages(tid)
    setup_success = True
    for msg in msgs:
        setup_success = setup_success and msg['level'] != 'error'
    server.setup = setup_success
    db.session.commit()



@celery.task(bind=True)
def configure_gluu_server(self, server_id, conffile):
    server = LDAPServer.query.get(server_id)
    tid = self.request.id
    chdir = '/opt/gluu-server-'+server.gluu_version

    wlogger.log(tid, "Connecting to the server %s" % server.hostname)
    c = RemoteClient(server.hostname)
    try:
        c.startup()
    except Exception as e:
        wlogger.log(tid, "Cannot establish SSH connection {0}".format(e),
                    "error")

    wlogger.log(tid, "Retrying with the IP address")
    c = RemoteClient(server.ip)
    try:
        c.startup()
    except Exception as e:
        wlogger.log(tid, "Cannot establish SSH connection {0}".format(e),
                    "error")
        wlogger.log(tid, "Ending server setup process.", "error")
        return False

    # Since it is a Gluu Server, a number of checks can be avoided
    # 1. Check if OpenLDAP is installed
    # 2. Check if symas-openldap.conf files exists
    # 3. Check for certificates - They will be at /etc/certs

    # 4. Existance of data directories - this is necassr check as we will be
    #    enabling accesslog DIT, maybe others by admin in the conf editor
    wlogger.log(tid, "Checking existing data and schema folders for LDAP")
    conf = open(conffile, 'r')
    for line in conf:
        if re.match('^directory', line):
            folder = line.split()[1]
            if not c.exists(os.path.join(chdir, folder)):
                run_command(tid, c, 'mkdir -p '+folder, chdir)
            else:
                wlogger.log(tid, folder, 'success')

    # 5. Gluu Schema file will be present - no checks required

    # 6. Copy User's custom schema files if any
    schemas = os.listdir(app.config['SCHEMA_DIR'])
    if len(schemas):
        wlogger.log(tid, "Copying custom schema files to the server")
        for schema in schemas:
            local = os.path.join(app.config['SCHEMA_DIR'], schema)
            remote = chdir+"/opt/gluu/schema/openldap/"+schema
            upload_file(tid, c, local, remote)

    # 7. Copy the slapd.conf
    wlogger.log(tid, "Copying slapd.conf file to the server")
    upload_file(tid, c, conffile, chdir+"/opt/symas/etc/openaldap/slapd.conf")

    wlogger.log(tid, "Restarting LDAP server to validate slapd.conf")
    # IMPORTANT:
    # Restart allows the server to create the mdb files for accesslog so
    # slaptest doesn't throw errors during OLC generation
    run_command(tid, c, 'service solserver restart', chdir)

    # 8. Download openldap.crt to be used in other servers for ldaps
    wlogger.log(tid, "Downloading SSL Certificate to be used in other servers")
    remote = chdir + '/etc/certs/openldap.crt'
    local = os.path.join(app.config["CERTS_DIR"],
                         "{0}.crt".format(server.hostname))
    download_file(tid, c, remote, local)

    # 9. Generate OLC slapd.d
    wlogger.log(tid, "Convert slapd.conf to slapd.d OLC")
    run_command(tid, c, 'service solserver stop', chdir)
    run_command(tid, c, "rm -rf /opt/symas/etc/openldap/slapd.d", chdir)
    run_command(tid, c, "mkdir /opt/symas/etc/openldap/slapd.d", chdir)
    run_command(tid, c, "/opt/symas/bin/slaptest -f /opt/symas/etc/openldap/"
                "slapd.conf -F /opt/symas/etc/openldap/slapd.d", chdir)

    # 10. Reset ownerships
    run_command(tid, c, "chown -R ldap:ldap /opt/gluu/data", chdir)
    run_command(tid, c, "chown -R ldap:ldap /opt/gluu/schema/openldap", chdir)
    run_command(tid, c, "chown -R ldap:ldap /opt/symas/etc/openldap/slapd.d",
                chdir)

    # 11. Restart the solserver with the new OLC configuration
    wlogger.log(tid, "Restarting LDAP server with OLC configuration")
    log = run_command(tid, c, "service solserver start", chdir)
    if 'failed' in log:
        wlogger.log(tid, "There seems to be some issue in starting the server."
                    "Running LDAP server in debug mode for troubleshooting")
        run_command(tid, c, "service solserver start -d 1", chdir)

    # Everything is done. Set the flag to based on the messages
    msgs = wlogger.get_messages(tid)
    setup_success = True
    for msg in msgs:
        setup_success = setup_success and msg['level'] != 'error'
    server.setup = setup_success
    db.session.commit()
