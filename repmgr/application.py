import redis
import json

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from celery import Celery


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
        return "repmgr:{}".format(taskid)

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


app = Flask(__name__)
app.config.from_object('repmgr.config.DevelopmentConfig')
db = SQLAlchemy(app)
celery = make_celery(app)
wlogger = WebLogger(app)

from .views import *
from .tasks import *
