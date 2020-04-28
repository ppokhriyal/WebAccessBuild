from datetime import datetime
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from webaccessbuild import db, login_manager, app
from flask_login import UserMixin


@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))


class User(db.Model,UserMixin):
	__bind_key__ = 'users'
	id = db.Column(db.Integer,primary_key=True)
	username = db.Column(db.String(20),unique=True,nullable=False)
	email = db.Column(db.String(120),unique=True,nullable=False)
	password = db.Column(db.String(60),nullable=False)
	password_decrypted = db.Column(db.String(60),nullable=False)
	reg_host_node = db.relationship('RegisteredNode',backref='register_host_node',lazy=True,cascade='all,delete-orphan')
	pb_info = db.relationship('PB',backref='pb_author',lazy=True,cascade='all,delete-orphan')

	def __repr__(self):
		return f"User('{self.username}','{self.email}','{self.reg_host_node}')"


class PB(db.Model):
	__bind_key__ = 'pb'
	id = db.Column(db.Integer,primary_key=True)
	pb_buildid = db.Column(db.Integer,unique=True,nullable=False)
	pb_pkgname = db.Column(db.String(60),nullable=False)
	pb_patchname = db.Column(db.String(60))
	pb_date_posted = db.Column(db.DateTime(),nullable=False,default=datetime.now)
	pb_description = db.Column(db.Text,nullable=False)
	pb_os_arch = db.Column(db.Text,nullable=False)
	pb_md5sum_pkg = db.Column(db.String(50),nullable=False)
	pb_md5sum_patch = db.Column(db.String(50))
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

	def __repr__(self):
		return f"Pkgdetails('{self.pb_buildid}','{self.pb_pkgname}','{self.pb_description}')"


class RegisteredNode(db.Model):
	__bind_key__ = 'registernode'
	id = db.Column(db.Integer,primary_key=True)
	ipaddress = db.Column(db.String(20),unique=True,nullable=False)
	hostname = db.Column(db.String(20),nullable=False)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

	def __repr__(self):

		return f"{self.ipaddress}"