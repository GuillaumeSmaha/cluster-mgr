from contextlib import contextmanager

import ldap


@contextmanager
def ldap_conn(hostname, port, user, passwd, starttls=False):
    """Establishes connection to LDAP and releases the connection
    after being used.

    This function handles 2 different schemes (``ldap`` and ``ldaps``).
    The first-class scheme is ``ldap`` (enabling TLS is recommended).
    If it can't establish the connection, this function will try
    to use ``ldaps`` scheme. Otherwise, exception will be raised.

    Example::

        with ldap_conn(hostname, port, user, passwd) as conn:
            conn.search_s()
    """
    try:
        conn = ldap.initialize('ldap://{}:{}'.format(hostname, port))
        if starttls:
            conn.start_tls_s()
        conn.bind_s(user, passwd)
        yield conn
    except ldap.SERVER_DOWN:
        conn = ldap.initialize('ldaps://{}:{}'.format(hostname, port))
        conn.bind_s(user, passwd)
        yield conn
    except ldap.LDAPError as exc:
        print exc
        raise
    finally:
        conn.unbind()


def search_from_ldap(conn, base, scope=ldap.SCOPE_BASE,
                     filterstr="(objectClass=*)",
                     attrlist=None, attrsonly=0):
    """Searches entries in LDAP.
    """
    try:
        result = conn.search_s(base, scope)
        ret = result[0]
    except ldap.NO_SUCH_OBJECT:
        ret = ("", {},)
    return ret
