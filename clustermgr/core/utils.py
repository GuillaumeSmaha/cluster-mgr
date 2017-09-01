import re
import os
import hashlib
import string
import random

from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers import modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend


DEFAULT_CHARSET = string.ascii_uppercase + string.digits + string.lowercase


def parse_slapdconf(old_conf=None):
    """Parses the slapd.conf file generated during the installation of
    Gluu server and gets the values necessary for the provider.conf.

    Args:
        old_conf (string) - OPTIONAL Location of the slapd.conf file.
            Defatuls to /opt/symas/etc/openldap/slapd.conf

    Returns:
        dict containing the values for the following
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


def ldap_encode(password):
    salt = os.urandom(4)
    sha = hashlib.sha1(password)
    sha.update(salt)
    b64encoded = '{0}{1}'.format(sha.digest(), salt).encode('base64').strip()
    encrypted_password = '{{SSHA}}{0}'.format(b64encoded)
    return encrypted_password


def generate_random_key(length=32):
    """Generates random key.
    """
    return os.urandom(length)


def generate_random_iv(length=8):
    """Generates random initialization vector.
    """
    return os.urandom(length)


def encrypt_text(text, key, iv):
    """Encrypts plain text using Blowfish and CBC.

    Example::

        import os
        # keep the same key and iv for decrypting the text
        key = os.urandom(32)
        iv = os.urandom(8)
        enc_text = encrypt_text("secret-text", key, iv)
    """
    cipher = Cipher(algorithms.Blowfish(key), modes.CBC(iv),
                    backend=default_backend())
    encryptor = cipher.encryptor()

    # CBC requires padding
    padder = padding.PKCS7(algorithms.Blowfish.block_size).padder()
    padded_data = padder.update(text) + padder.finalize()

    # encrypt the text
    encrypted_text = encryptor.update(padded_data) + encryptor.finalize()
    return encrypted_text


def decrypt_text(encrypted_text, key, iv):
    """Decrypts encrypted text using Blowfish and CBC.

    Example::

        # use the same key and iv used in encrypting the text
        text = decrypt_text(enc_text, key, iv)
    """
    cipher = Cipher(algorithms.Blowfish(key), modes.CBC(iv),
                    backend=default_backend())
    decryptor = cipher.decryptor()

    # CBC requires padding
    unpadder = padding.PKCS7(algorithms.Blowfish.block_size).unpadder()
    padded_data = decryptor.update(encrypted_text) + decryptor.finalize()

    # decrypt the encrypted text
    text = unpadder.update(padded_data) + unpadder.finalize()
    return text


def random_chars(size=12, chars=DEFAULT_CHARSET):
    """Returns a string of random alpha-numeric characters.

    Args:
        size (int, optional): the length of the string. Defaults to 12
        chars (string, optional): a selection of characters to pick the random
            ones for the return string

    Returns:
        a string of random characters
    """
    return ''.join(random.choice(chars) for _ in range(size))
