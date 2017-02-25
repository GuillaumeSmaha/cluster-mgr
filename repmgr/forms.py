from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, IntegerField
from wtforms.validators import DataRequired


class NewProviderForm(FlaskForm):
    hostname = StringField('Hostname', validators=[DataRequired()])
    port = IntegerField('Port', validators=[DataRequired()])
    starttls = BooleanField('Use StartTLS for communication', default=False)
    admin_pw = StringField('LDAP Admin Password', validators=[DataRequired()])
    replication_pw = StringField('Replication Password',
                                 validators=[DataRequired()])
    tls_cacert = StringField('TLS CA Certificate')
    tls_servercert = StringField('TLS Server Certificate')
    tls_serverkey = StringField('TLS Server Cert Key')


class NewConsumerForm(FlaskForm):
    hostname = StringField('Hostname', validators=[DataRequired()])
    port = IntegerField('Port', validators=[DataRequired()])
    starttls = BooleanField('Use StartTLS for communication', default=False)
    admin_pw = StringField('LDAP Admin Password', validators=[DataRequired()])
    tls_cacert = StringField('TLS CA Certificate')
    tls_servercert = StringField('TLS Server Certificate')
    tls_serverkey = StringField('TLS Server Cert Key')
    provider = SelectField('Provider', coerce=int)
