import os
from datetime import timedelta


class Config(object):
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = ''
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'prettysecret'
    BASE_DN = 'o=gluu'
    CELERY_BROKER_URL = 'redis://localhost:6379'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379'
    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_LOG_DB = 0
    OX11_PORT = '8190'
    SCHEDULE_REFRESH = 30.0
    CELERYBEAT_SCHEDULE = {
        'add-every-30-seconds': {
            'task': 'clustermgr.tasks.schedule_key_rotation',
            'schedule': timedelta(seconds=SCHEDULE_REFRESH),
            'args': (),
        },
    }
    DATA_DIR = os.environ.get(
        "DATA_DIR",
        os.path.join(os.path.expanduser("~"), ".clustermgr"),
    )
    JAVALIBS_DIR = os.path.join(DATA_DIR, "javalibs")
    JKS_PATH = os.path.join(DATA_DIR, "oxauth-keys.jks")
    APP_INSTANCE_DIR = os.path.join(DATA_DIR, "instance")
    SCHEMA_DIR = os.path.join(DATA_DIR, "schema")
    SLAPDCONF_DIR = os.path.join(DATA_DIR, "slapdconf")


class ProductionConfig(Config):
    SECRET_KEY = ''
    DATA_DIR = os.environ.get("DATA_DIR", "/opt/gluu-cluster-mgr")
    JAVALIBS_DIR = os.path.join(DATA_DIR, "javalibs")
    JKS_PATH = os.path.join(DATA_DIR, "oxauth-keys.jks")
    APP_INSTANCE_DIR = os.path.join(DATA_DIR, "instance")
    SCHEMA_DIR = os.path.join(DATA_DIR, "schema")
    SLAPDCONF_DIR = os.path.join(DATA_DIR, "slapdconf")
    SQLALCHEMY_DATABASE_URI = "sqlite:///{}/clustermgr.db".format(DATA_DIR)


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///{}/clustermgr.dev.db".format(Config.DATA_DIR)
    SQLALCHEMY_TRACK_MODIFICATIONS = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite://:memory:'
