try:
    from flask_wtf import FlaskForm
except ImportError:
    from flask_wtf import Form as FlaskForm
from wtforms import StringField, SelectField, BooleanField, IntegerField, \
    PasswordField, RadioField, SubmitField
from wtforms.validators import DataRequired, Regexp, AnyOf, \
    ValidationError, URL
from flask_wtf.file import FileField, FileRequired


class NewProviderForm(FlaskForm):
    gluu_server = BooleanField('This is a Gluu Server (Uncheck for plain OpenLDAP installations)', default=False)
    gluu_version = SelectField('Gluu Server Version', choices=[('3.0.1', '3.0.1')])
    hostname = StringField('Hostname *', validators=[DataRequired()])
    port = IntegerField('Port *', validators=[DataRequired()])
    admin_pw = PasswordField('LDAP Admin Password *', validators=[DataRequired()])
    starttls = BooleanField('Use StartTLS for communication', default=False)
    tls_cacert = StringField('TLS CA Certificate')
    tls_servercert = StringField('TLS Server Certificate')
    tls_serverkey = StringField('TLS Server Cert Key')


class NewConsumerForm(FlaskForm):
    hostname = StringField('Hostname', validators=[DataRequired()])
    port = IntegerField('Port', validators=[DataRequired()])
    starttls = BooleanField('Use StartTLS for communication', default=False)
    admin_pw = PasswordField('LDAP Admin Password', validators=[DataRequired()])  # noqa
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
    admin_pw1 = PasswordField('LDAP Admin Password', validators=[DataRequired()])  # noqa
    admin_pw2 = PasswordField('LDAP Admin Password', validators=[DataRequired()])  # noqa
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
            message="Only alphabets and space allowed; cannot end with space.")])  # noqa
    replication_pw = PasswordField('Replication Manager Password',
                                   validators=[DataRequired()])
    certificate_folder = StringField('Certificate Folder')
    update = SubmitField("Update Configuration")


class SchemaForm(FlaskForm):
    schema = FileField(validators=[FileRequired()])
    upload = SubmitField("Upload Schema")


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

    def validate_oxeleven_url(form, field):
        if not field.data and form.type.data == "oxeleven":
            raise ValidationError("This field is required if oxEleven is "
                                  "selected as rotation type")

    def validate_oxeleven_token(form, field):
        if not field.data and form.type.data == "oxeleven":
            raise ValidationError("This field is required if oxEleven is "
                                  "selected as rotation type")


class LoggingServerForm(FlaskForm):
    # mq_host = StringField("Hostname", validators=[DataRequired()])
    # mq_port = IntegerField("Port", validators=[DataRequired()])
    # mq_user = StringField("User", validators=[DataRequired()])
    # mq_password = PasswordField("Password", validators=[DataRequired()])
    # db_host = StringField("Hostname", validators=[DataRequired()])
    # db_port = IntegerField("Port", validators=[DataRequired()])
    # db_user = StringField("User", validators=[DataRequired()])
    # db_password = PasswordField("Password", validators=[DataRequired()])
    url = StringField("URL", validators=[DataRequired(),
                                         URL(require_tld=False)])
