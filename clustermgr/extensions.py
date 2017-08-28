from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from celery import Celery

from .weblogger import WebLogger

from clustermgr.config import Config

try:
    from flask_wtf.csrf import CSRFProtect
except ImportError:
    # backward-compatibility
    from flask_wtf.csrf import CsrfProtect as CSRFProtect


db = SQLAlchemy()
csrf = CSRFProtect()
migrate = Migrate()
wlogger = WebLogger()
celery = Celery('clustermgr.application', backend=Config.CELERY_RESULT_BACKEND,
                broker=Config.CELERY_BROKER_URL
                )
