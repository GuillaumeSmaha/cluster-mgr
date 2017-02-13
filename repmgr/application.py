from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config.from_object('repmgr.config.DevelopmentConfig')
db = SQLAlchemy(app)

from .views import *

