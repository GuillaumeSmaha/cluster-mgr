import os
import shlex
import subprocess


DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".repmgr")
JAVALIBS_DIR = os.path.join(DEFAULT_DATA_DIR, "javalibs")
JKS_PATH = os.path.join(DEFAULT_DATA_DIR, "oxauth-keys.jks")


def exec_cmd(cmd):
    args = shlex.split(cmd)
    popen = subprocess.Popen(args,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    stdout, stderr = popen.communicate()
    retcode = popen.returncode
    return stdout, stderr, retcode


def generate_jks(passwd, exp=365, alg="RS512"):
    if not os.path.exists(JAVALIBS_DIR):
        os.makedirs(JAVALIBS_DIR)

    if os.path.exists(JKS_PATH):
        os.unlink(JKS_PATH)

    cmd = " ".join([
        "java", "-Dlog4j.defaultInitOverride=true",
        "-cp", "'{}/*'".format(JAVALIBS_DIR),
        "org.xdi.oxauth.util.KeyGenerator",
        "-algorithms", alg,
        "-dnname", "{!r}".format("CN=oxAuth CA Certificates"),
        "-expiration", "{}".format(exp),
        "-keystore", JKS_PATH,
        "-keypasswd", passwd,
    ])
    return exec_cmd(cmd)
