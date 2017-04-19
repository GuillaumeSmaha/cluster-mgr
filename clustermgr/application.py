import redis
import json
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
from flask_script import Manager
from flask_migrate import Migrate, MigrateCommand


def make_celery(app):
    celery = Celery(app.import_name,
                    backend=app.config['CELERY_RESULT_BACKEND'],
                    broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery


class WebLogger():
    def __init__(self, app):
        host = app.config['REDIS_HOST']
        port = app.config['REDIS_PORT']
        db = app.config['REDIS_LOG_DB']

        self.r = redis.Redis(host=host, port=port, db=db)

    def __key(self, taskid):
        return "clustermgr:{}".format(taskid)

    def log(self, taskid, message, level=None, **kwargs):
        """Logs the message into REDIS as a list for that task id"""
        logitem = {'msg': message}
        if level:
            logitem['level'] = level
        else:
            logitem['level'] = 'info'

        for k, v in kwargs.iteritems():
            logitem[k] = v

        self.r.rpush(self.__key(taskid), json.dumps(logitem))

    def get_messages(self, taskid):
        messages = self.r.lrange(self.__key(taskid), 0, -1)
        if not messages:
            return []
        return [json.loads(msg) for msg in messages]

    def clean(self, taskid):
        """Removes the log for the particular task id"""
        self.r.delete(self.__key(taskid))


def _get_app_config():
    app_mode = os.environ.get("APP_MODE")
    if app_mode == "prod":
        cfg = "clustermgr.config.ProductionConfig"
    elif app_mode == "test":
        cfg = "clustermgr.config.TestConfig"
    else:
        cfg = "clustermgr.config.DevelopmentConfig"
    return cfg


app = Flask(__name__)
app.config.from_object(_get_app_config())
app.instance_path = app.config["APP_INSTANCE_DIR"]
# allow custom config
app.config.from_pyfile(
    os.path.join(app.instance_path, "config.py"),
    silent=True,
)

db = SQLAlchemy(app)

celery = make_celery(app)

wlogger = WebLogger(app)

migrate = Migrate(
    app, db, directory=os.path.join(os.path.dirname(__file__), "migrations"),
)

manager = Manager(app)
manager.add_command("db", MigrateCommand)

# setup the instance's working directories
if not os.path.isdir(app.config['SCHEMA_DIR']):
    os.makedirs(app.config['SCHEMA_DIR'])
if not os.path.isdir(app.config['SLAPDCONF_DIR']):
    os.makedirs(app.config['SLAPDCONF_DIR'])
if not os.path.isdir(app.config['LDIF_DIR']):
    os.makedirs(app.config['LDIF_DIR'])
if not os.path.isdir(app.instance_path):
    os.makedirs(app.instance_path)


def cli():
    manager.run()

from .views import *  # noqa
from .tasks import *  # noqa
