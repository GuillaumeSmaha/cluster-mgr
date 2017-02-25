import ldap

ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)


def setup_replication_user():
    con = ldap.initialize('ldap://provider.example.com')
    con.start_tls_s()
    con.bind_s('cn=directory manager,o=gluu', 'secret')

    replication_user = [
            ('objectclass', ['person']),
            ('cn', ['replicator']),
            ('sn', ['gluu']),
            ('userpassword', ['super_secret'])
            ]
    dn = 'cn=replicator,o=gluu'

    con.add_s(dn, replication_user)
    con.unbind()


if __name__ == '__main__':
    setup_replication_user()
