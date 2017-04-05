import codecs
import os
import re
from setuptools import setup
from setuptools import find_packages


def find_version(*file_paths):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, *file_paths), 'r') as f:
        version_file = f.read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name='repmgr',
    version=find_version("repmgr", "__init__.py"),
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=[
        "Flask",
        "python-ldap",
        "flask-wtf",
        "celery",
        "fabric",
        "flask-sqlalchemy",
        "redis",
        "cryptography",
        "requests",
        "flask-migrate",
    ],
    entry_points={
        "console_scripts": ["repmgr-cli=repmgr.application:cli"],
    },
)
