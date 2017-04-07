import os


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
    DATA_DIR = os.environ.get(
        "DATA_DIR",
        os.path.join(os.path.expanduser("~"), ".clustermgr"),
    )
    APP_INSTANCE_DIR = os.path.join(DATA_DIR, "instance")
    SCHEMA_DIR = os.path.join(DATA_DIR, "schema")
    SLAPDCONF_DIR = os.path.join(DATA_DIR, "slapdconf")


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = ''
    SECRET_KEY = ''


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///{}/clustermgr.dev.db".format(Config.DATA_DIR)
    SQLALCHEMY_TRACK_MODIFICATIONS = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite://:memory:'
