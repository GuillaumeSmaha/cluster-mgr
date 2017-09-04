"""weblogger.py - flask extension providing storage facility via Redis.
"""

import redis
import json


class WebLogger(object):
    """WebLogger is a Redis wrapper to store task logs for flask view access.

    In situations where a long running task generates logs which must be sent
    to the client upon request, there is a necessity to store the logs for a
    short duration. The tasks might also generate information like subtask
    status, intermediatary results ..etc, These information might be presented
    to the user in multiple ways like check lists, console logs ..etc.,

    For such situations there is a requirement for a common short time storage
    of information which can be accessed from both the tasks and flask views.
    WebLogger provides a wrapper over Redis to do just that.

    Configuration:
        By default WebLogger connects to whatever is the default in redis-py
        using redis.Redis() instance. This can be overridden by setting the
        following values in the Flask application config:
        REDIS_HOST, REDIS_PORT, REDIS_LOG_DB

    Initialization::

        from flask import Flask
        from .weblogger import WebLogger

        app = Flask(__name__)
        wlogger = WebLogger(app)

        # or lazily
        wlogger = WebLogger()
        wlogger.init_app(app)

    Warning: In case of lazy initialization the redis instance is
        initialized with default values redis://localhost:6379/0. If a redis
        instance is running, then data can be stored in redis outside of the
        flask application context. The data will be logged with the keys using
        the prefix `weblogger`

    Logging:
        Refer log()

    Retrival:
        Refer get_messages()

    Cleanup:
        Refer clean()
    """
    def __init__(self, app=None):
        self.app = app
        self.r = redis.Redis()
        self.prefix = 'weblogger'
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        host = app.config['REDIS_HOST']
        port = app.config['REDIS_PORT']
        db = app.config['REDIS_LOG_DB']
        self.prefix = app.name

        self.r.connection_pool.disconnect()
        self.r = redis.Redis(host=host, port=port, db=db)

    def __key(self, taskid):
        return "{0}:{1}".format(self.prefix, taskid)

    def log(self, taskid, message, level=None, **kwargs):
        """R Pushes the message into REDIS as a list for that task id with the key
        <app.name>:<taskid>.

        The message passed on would be converted to a dictionary with the
        structure:
        { 'msg : <your_message>, 'level': <your_level>,
          'other_keys_from_kwargs': <kwarg_value>
        }
        This dictionary would be json dumped into a string and Rpushed into the
        redis with the key `<app.name>:<task_id>`

        Args:
            taskid (string) - a unique id to identify the task
            message (string) - the log message to be stored
            level (string)  - levels like 'info', 'debug'. Defaults to info
        """
        logitem = {'msg': message.strip()}
        if level:
            logitem['level'] = level
        else:
            logitem['level'] = 'info'

        for k, v in kwargs.iteritems():
            logitem[k] = v

        self.r.rpush(self.__key(taskid), json.dumps(logitem))

    def get_messages(self, taskid):
        """Returns all the messages pushed by a task.

        Args:
            taskid (string) - The unique id of the task

        Returns:
            list of dicts containing all the messages posted with the given
            task id
        """
        messages = self.r.lrange(self.__key(taskid), 0, -1)
        if not messages:
            return []
        return [json.loads(msg) for msg in messages]

    def clean(self, taskid):
        """Removes the log for the particular task id

        Args:
            taskid (string) - the unique id of the task
        """
        self.r.delete(self.__key(taskid))
