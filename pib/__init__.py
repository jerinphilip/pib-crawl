from flask import Flask, render_template, request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pib-crawled-sqlite.db"

db = SQLAlchemy(app)

from . import models as M

is_sqlite = True
migrate = Migrate(app, db, render_as_batch=is_sqlite)

from .docstore import docstore

app.register_blueprint(docstore)
