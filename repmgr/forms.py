from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, IntegerField, \
        PasswordField
from wtforms.validators import DataRequired


class NewServerForm(FlaskForm):
    host = StringField('Hostname', validators=[DataRequired()], description="Hostname of the server")
    port = IntegerField('Port', validators=[DataRequired()], description="LDAP port used for accessing the server")
    starttls = BooleanField('startTLS', default=False)
    role = SelectField('Role', choices=[('master', 'Master'), ('consumer', 'Consumer')])
    server_id = IntegerField('Server ID')
    replication_id = IntegerField('Replication ID')


class NewMasterForm(FlaskForm):
    hostname = StringField('Hostname', validators=[DataRequired()])
    port = IntegerField('Port', validators=[DataRequired()])
    starttls = BooleanField('StartTLS', default=False)
    server_id = IntegerField('Server ID')
    replication_id = IntegerField('Replication ID')
    manager_dn = StringField('Replication Manager DN')
    manager_pw = PasswordField('Replication Manager Password')
