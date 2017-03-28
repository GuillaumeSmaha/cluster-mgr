import re


def parse_slapdconf(old_conf=None):
    """Parses the slapd.conf file generated during the installation of
    Gluu server and gets the values necessary for the provider.conf.

    Args:
        old_conf (string) - OPTIONAL Location of the slapd.conf file.
            Defatuls to /opt/symas/etc/openldap/slapd.conf

    Returns:
        dict containing the values for the following:
        * openldapSchemaFolder
        * openldapTLSCACert
        * openldapTLSCert
        * openldapTLSKey
        * encoded_ldap_pw
        * BCRYPT - This has {} around it, so an escape value `{BCRYPT}`
    """
    if not old_conf:
        old_conf = '/opt/symas/etc/openldap/slapd.conf'

    f = open(old_conf, 'r')
    values = {}

    for line in f:
        # openldapSchemaFolder
        if 'gluu.schema' in line and re.match('^include*', line):
            path = line.split("\"")[1].replace("/gluu.schema", "")
            values["openldapSchemaFolder"] = path
        # openldapTLSCACert
        if re.match("^TLSCACertificateFile*", line):
            values["openldapTLSCACert"] = line.split("\"")[1]
        # openldapTLSCert
        if re.match("^TLSCertificateFile*", line):
            values["openldapTLSCert"] = line.split("\"")[1]
        # openldapTLSKey
        if re.match("^TLSCertificateKeyFile*", line):
            values["openldapTLSKey"] = line.split("\"")[1]
        # encoded_ldap_pw
        if re.match("^rootpw", line):
            values["encoded_ldap_pw"] = line.split()[1]
    f.close()

    # BCRYPT - This has {} around it so escape this
    values["BCRYPT"] = "{BCRYPT}"

    return values
