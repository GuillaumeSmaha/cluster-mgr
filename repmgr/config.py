from datetime import timedelta

class Config(object):
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = 'sqlite://:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'prettysecret'
    BASE_DN = 'o=gluu'
    CELERY_BROKER_URL = 'redis://localhost:6379'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379'
    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_LOG_DB = 0
    OX11_PORT = '8190'
    # CELERYBEAT_SCHEDULE = {
    #     'add-every-5-seconds': {
    #         'task': 'repmgr.tasks.add', # notice that the complete name is needed
    #         'schedule': timedelta(seconds=5),
    #         'args': (600, 66)
    #     },
    # }
    #CELERY_TIMEZONE = 'BST'
    SCHEDULE_REFRESH = 30.0


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = ''
    SECRET_KEY = ''


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/repmgr.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
