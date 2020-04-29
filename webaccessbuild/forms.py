from flask_wtf import FlaskForm
from flask_mde import Mde, MdeField
from flask_wtf.file import FileField, FileAllowed
from flask_login import current_user
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, SelectField,IntegerField
from wtforms.ext.sqlalchemy.fields import QuerySelectField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, InputRequired,IPAddress
from webaccessbuild.models import User,PB,RegisteredNode,FB


#Login Form
class LoginForm(FlaskForm):
	email = StringField('Email',validators=[DataRequired(),Email()])
	password = PasswordField('Password',validators=[DataRequired()])
	submit = SubmitField('Login')

#Registration Form
class RegistrationForm(FlaskForm):

	username = StringField('Username',validators=[DataRequired(),Length(min=2,max=20)])
	email = StringField('Email',validators=[DataRequired(),Email()])
	password = PasswordField('Password',validators=[DataRequired()])
	confirm_password = PasswordField('Confirm Password',validators=[DataRequired(),EqualTo('password')])
	submit = SubmitField('Sign Up')

	def validate_username(self,username):
		user = User.query.filter_by(username=username.data).first()
		if user:
			raise ValidationError('That username is taken. Please choose a diffrent one.')

	def validate_email(self,email):
		user = User.query.filter_by(email=email.data).first()
		check_email_valid = email.data
		if check_email_valid.split('@')[1] != "vxlsoftware.com":
			raise ValidationError('Please enter your valid vxlsoftware email id.')
		if user:
		   raise ValidationError('That email is taken. Please choose a diffrent one.')

#PB Package Build Form
class PBBuildForm(FlaskForm):
	pb_pkgbuildid = StringField('Package Build ID',render_kw={'readonly':True},validators=[DataRequired()])
	pb_pkgname = StringField('Package Name',validators=[DataRequired()])
	pb_pkgdescription = TextAreaField('Description',validators=[DataRequired()])
	pb_osarch = SelectField('OS Architecture',choices=[('32-Bit','32-Bit'),('64-Bit','64-Bit'),('Multi-Arch','Multi-Arch')])
	remote_host_ip = QuerySelectField(query_factory=lambda:RegisteredNode.query.all())
	pb_rawpkgpath = StringField('Package Structure',validators=[DataRequired()])
	pb_needpatch = BooleanField('Required Patch')
	pb_patchtype = SelectField('Patch Format',choices=[('Current Patch','Current Patch'),('Legacy Patch','Legacy Patch')])
	pb_patchname = StringField('Patch Name')
	pb_removepkg = TextAreaField('Remove Packages')
	pb_install_script = TextAreaField('Install Script')
	pb_submit = SubmitField('Build')


	def validate_pb_pkgname(self,pb_pkgname):
		l = ['apps:','basic:','core:']
		FLAG="flase"

		if pb_pkgname.data.casefold()[:5] in l :
			FLAG="true"

		if pb_pkgname.data.casefold()[:6] in l:
			FLAG="true"

		if FLAG == "flase":
			raise ValidationError("Please Check the Package name")	

#PB Add Host
class PBAddHostForm(FlaskForm):
	pb_remote_host_ip = StringField('Remote Host IP Address',validators=[DataRequired(),IPAddress(message="Please Give Valid IP-Address")])
	pb_submit = SubmitField('Register')


#Firmware Update Patch Form
#FB Build Info
class FBBuildForm(FlaskForm):

	fb_buildid = StringField('Firmware Build ID',render_kw={'readonly':True},validators=[DataRequired()])
	fb_name = StringField('Firmware Name',validators=[DataRequired()])
	fb_description = TextAreaField('Description',validators=[DataRequired()])
	fb_osarch = SelectField('OS Architecture',choices=[('32','32-Bit'),('64','64-Bit'),('Multi-Arch','Multi-Arch')])
	fb_type = SelectField('Patch Format',choices=[('Current Patch','Current Patch'),('Legacy Patch','Legacy Patch')])
	fb_min_img_build = IntegerField('Minimum',validators=[DataRequired("Only Integer value is allowed and value less than 1 not allowed")])
	fb_max_img_build = IntegerField('Maximum',validators=[DataRequired("Only Integer value is allowed and value less than 1 not allowed")])
	fb_add = TextAreaField('Add')
	fb_remove = TextAreaField('Remove')
	fb_install_script = TextAreaField('install')
	fb_submit = SubmitField('Build')

	def validate_min_max_value(self,fb_min_img_build,fb_max_img_build):

		if fb_min_img_build.data > fb_max_img_build.data :

			raise ValidationError("Minimum value cannot be greater then Maximum value")