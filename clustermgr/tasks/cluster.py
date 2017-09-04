import re
import os

from flask import current_app as app

from clustermgr.models import LDAPServer
from clustermgr.extensions import celery, wlogger
from clustermgr.core.remote import RemoteClient


def run_command(tid, c, command):
    wlogger.log(tid, command, "debug")
    cin, cout, cerr = c.run(command)
    output = ''
    if cout:
        wlogger.log(tid, cout, "debug")
        output = cout
    if cerr:
        wlogger.log(tid, cerr, "error")
        output += "\n" + cerr
    return output


def upload_file(tid, c, local, remote):
    out = c.upload(local, remote)
    wlogger.log(tid, out, 'error' if 'Error' in out else 'success')


@celery.task(bind=True)
def setup_provider(self, server_id, conffile):
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

    wlogger.log(tid, "Checking status of LDAP server")
    status = run_command(tid, c, 'service solserver status')

    if 'is running' in status:
        wlogger.log(tid, "Stopping LDAP Server")
        run_command(tid, c, 'service solserver stop')

    # 8. Generate OLC slapd.d
    wlogger.log(tid, "Generating slapd.d Online Configuration")
    run_command(tid, c, 'rm -rf /opt/symas/etc/openldap/slapd.d')
    run_command(tid, c, 'mkdir -p /opt/symas/etc/openldap/slapd.d')
    run_command(tid, c,
                '/opt/symas/bin/slaptest -f /opt/symas/etc/openldap/slapd.conf'
                ' -F /opt/symas/etc/openldap/slapd.d')

    # 9. Restart the solserver with the new configuration
    wlogger.log(tid, "Starting LDAP server")
    log = run_command(tid, c, 'service solserver start')
    if 'failed' in log:
        wlogger.log(tid, "OpenLDAP server failed to start.", "error")
        wlogger.log(tid, "Debugging slapd...", "info")
        run_command(tid, "service solserver start -d 1")
