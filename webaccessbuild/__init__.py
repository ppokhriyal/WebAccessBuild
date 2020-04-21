from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

app = Flask(__name__)
app.config['SECRET_KEY'] = '878436c0a462c4145fa59eec2c43a66a'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config ['SQLALCHEMY_BINDS'] = {'users':'sqlite:///users.db','pb':'sqlite:///pb.db','fb':'sqlite:///fb.db','ib':'sqlite:///ib.db'}
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'user_login'
login_manager.login_message_category = 'info'

from webaccessbuild import routes