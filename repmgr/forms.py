from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, IntegerField, \
    PasswordField, RadioField
from wtforms.validators import DataRequired, Regexp, AnyOf


class NewProviderForm(FlaskForm):
    hostname = StringField('Hostname', validators=[DataRequired()])
    port = IntegerField('Port', validators=[DataRequired()])
    starttls = BooleanField('Use StartTLS for communication', default=False)
    admin_pw = PasswordField('LDAP Admin Password', validators=[DataRequired()])
    tls_cacert = StringField('TLS CA Certificate')
    tls_servercert = StringField('TLS Server Certificate')
    tls_serverkey = StringField('TLS Server Cert Key')


class NewConsumerForm(FlaskForm):
    hostname = StringField('Hostname', validators=[DataRequired()])
    port = IntegerField('Port', validators=[DataRequired()])
    starttls = BooleanField('Use StartTLS for communication', default=False)
    admin_pw = PasswordField('LDAP Admin Password', validators=[DataRequired()])
    tls_cacert = StringField('TLS CA Certificate')
    tls_servercert = StringField('TLS Server Certificate')
    tls_serverkey = StringField('TLS Server Cert Key')
    provider = SelectField('Provider', coerce=int)


class NewMirrorModeForm(FlaskForm):
    host1 = StringField('Hostname', validators=[DataRequired()])
    host2 = StringField('Hostname', validators=[DataRequired()])
    port1 = IntegerField('Port', validators=[DataRequired()])
    port2 = IntegerField('Port', validators=[DataRequired()])
    tls1 = BooleanField('Use StartTLS for communication', default=False)
    tls2 = BooleanField('Use StartTLS for communication', default=False)
    admin_pw1 = PasswordField('LDAP Admin Password', validators=[DataRequired()])
    admin_pw2 = PasswordField('LDAP Admin Password', validators=[DataRequired()])
    cacert1 = StringField('TLS CA Certificate')
    cacert2 = StringField('TLS CA Certificate')
    servercert1 = StringField('TLS Server Certificate')
    servercert2 = StringField('TLS Server Certificate')
    serverkey1 = StringField('TLS Server Cert Key')
    serverkey2 = StringField('TLS Server Cert Key')


class AppConfigForm(FlaskForm):
    replication_dn = StringField('Replication Manager DN', validators=[
        DataRequired(), Regexp(
            '^[a-zA-Z][a-zA-Z ]*[a-zA-Z]$',
            message="Only alphabets and space allowed; cannot end with space.")])
    replication_pw = PasswordField('Replication Manager Password',
                                   validators=[DataRequired()])
    certificate_folder = StringField('Certificate Folder')


class KeyRotationForm(FlaskForm):
    interval = IntegerField("Rotation Interval", validators=[DataRequired()])
    type = RadioField(
        "Rotation Type",
        choices=[("oxeleven", "oxEleven",), ("jks", "JKS")],
        validators=[AnyOf(["oxeleven", "jks"])],
    )
    oxeleven_url = StringField("oxEleven URL")
    oxeleven_token = PasswordField("oxEleven Token")
    inum_appliance = StringField("Inum Appliance", validators=[DataRequired()])
