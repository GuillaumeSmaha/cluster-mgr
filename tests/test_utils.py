import os
import unittest

from repmgr.utils import parse_slapdconf


class SlapdConfParseTest(unittest.TestCase):
    def test_parser(self):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        conf = os.path.join(current_dir, "data", "slapd.conf")
        values = parse_slapdconf(conf)
        self.assertEquals(values["openldapSchemaFolder"],
                          "/opt/gluu/schema/openldap")
        self.assertEquals(values["openldapTLSCACert"],
                          "/etc/certs/openldap.pem")
        self.assertEquals(values["openldapTLSCert"],
                          "/etc/certs/openldap.crt")
        self.assertEquals(values["openldapTLSKey"],
                          "/etc/certs/openldap.key")
        self.assertEquals(values["encoded_ldap_pw"],
                          "{SSHA}NtdgEfn/RjKonrJcvi2Qqn4qrk8ccedb")
        self.assertEquals(values["BCRYPT"], "{BCRYPT}")

