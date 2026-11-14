from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField, RadioField
from wtforms.validators import DataRequired, Email, Length, Optional

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

class RegisterForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=25)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign Up')

class ProfilSplitForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=25)])
    last_name = StringField('LastName', validators=[DataRequired()])
    phone = StringField('Phone', validators=[Optional(), Length(max=11)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Save')

class ProfilMainPassForm(FlaskForm):
    new_pass = PasswordField('NewPassword', validators=[DataRequired()])
    re_new_pass = PasswordField('ReNewPass', validators=[DataRequired()])
    submit = SubmitField('Save')

class ProfilAddSplit(FlaskForm):
    name = StringField('Name', validators=[Optional(), Length(max=40)])
    city = StringField('City', validators=[DataRequired(), Length(max=20)])
    street = StringField('Street', validators=[DataRequired(), Length(max=20)])
    home = StringField('Home', validators=[DataRequired(), Length(max=20)])
    flat = StringField('Flat')
    submit = SubmitField('Add')

class ProfilAddressForm(FlaskForm):
    radio = RadioField('Radio', validators=[DataRequired()])
