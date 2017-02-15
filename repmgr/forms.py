from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField
from wtforms.validators import DataRequired


class NewServerForm(FlaskForm):
    host = StringField('Hostname', validators=[DataRequired()], description="Hostname of the server")
    port = StringField('Port', validators=[DataRequired()], description="LDAP port used for accessing the server")
    starttls = BooleanField('startTLS', default=False)
    role = SelectField('Role', choices=[('master', 'Master'), ('consumer', 'Consumer')])
    server_id = StringField('Server ID')
    replication_id = StringField('Replication ID')
