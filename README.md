# Cluster Manager

GUI tool for managing Gluu Server OpenLDAP replication

## Installing Cluster Manager

Install prerequisites packages first. On debian or ubuntu, install them using `apt-get`:

```
sudo apt-get install build-essential libssl-dev libffi-dev python-dev openjdk-7-jre-headless
```

Note, OpenJDK or any JVM is required as Cluster Manager relies on several Java libraries.
After prerequisites packages already installed, we need to get some Java JAR files and put them
in predefined data directory (by default the location is `$HOME/.clustermgr/javalibs` directory).

```
mkdir -p $HOME/.clustermgr/javalibs
cd $HOME/.clustermgr/javalibs
wget -q http://central.maven.org/maven2/org/bouncycastle/bcpkix-jdk15on/1.54/bcpkix-jdk15on-1.54.jar
wget -q http://central.maven.org/maven2/org/bouncycastle/bcprov-jdk15on/1.54/bcprov-jdk15on-1.54.jar
wget -q http://central.maven.org/maven2/commons-cli/commons-cli/1.3.1/commons-cli-1.3.1.jar
wget -q http://central.maven.org/maven2/commons-codec/commons-codec/1.7/commons-codec-1.7.jar
wget -q http://central.maven.org/maven2/commons-io/commons-io/2.4/commons-io-2.4.jar
wget -q http://central.maven.org/maven2/commons-lang/commons-lang/2.6/commons-lang-2.6.jar
wget -q http://central.maven.org/maven2/commons-logging/commons-logging/1.1.1/commons-logging-1.1.1.jar
wget -q http://central.maven.org/maven2/com/google/guava/guava/19.0/guava-19.0.jar
wget -q http://central.maven.org/maven2/org/apache/httpcomponents/httpclient/4.3.6/httpclient-4.3.6.jar
wget -q http://central.maven.org/maven2/org/apache/httpcomponents/httpcore/4.3.3/httpcore-4.3.3.jar
wget -q http://central.maven.org/maven2/org/jboss/resteasy/jaxrs-api/2.3.7.Final/jaxrs-api-2.3.7.Final.jar
wget -q http://central.maven.org/maven2/org/codehaus/jettison/jettison/1.3/jettison-1.3.jar
wget -q http://central.maven.org/maven2/org/apache/logging/log4j/log4j-1.2-api/2.7/log4j-1.2-api-2.7.jar
wget -q http://central.maven.org/maven2/org/apache/logging/log4j/log4j-api/2.7/log4j-api-2.7.jar
wget -q http://central.maven.org/maven2/org/apache/logging/log4j/log4j-core/2.7/log4j-core-2.7.jar
wget -q https://ox.gluu.org/maven/org/xdi/oxauth-client/3.0.0/oxauth-client-3.0.0.jar
wget -q https://ox.gluu.org/maven/org/xdi/oxauth-model/3.0.0/oxauth-model-3.0.0.jar
wget -q https://ox.gluu.org/maven/org/gluu/oxeleven-client/3.0.0/oxeleven-client-3.0.0.jar
wget -q https://ox.gluu.org/maven/org/gluu/oxeleven-model/3.0.0/oxeleven-model-3.0.0.jar
wget -q http://central.maven.org/maven2/org/jboss/resteasy/resteasy-jaxrs/2.3.7.Final/resteasy-jaxrs-2.3.7.Final.jar
```

Clone this repo or download the source manually.

```
cd /path/to/replication-mgr
python setup.py install
```

## Running Cluster Manager

A successful installation will install a tool called `clustermgr-cli`.
Run the tool to initialize the database schema:

```
clustermgr-cli db upgrade
```

Before running the app, we need to create custom config file to override default configuration.
Create a file at `$HOME/.clustermgr/instance/config.py`. Here's an example of custom `config.py`:

```
DEBUG=False
TESTING=False
SQLALCHEMY_DATABASE_URI=/path/to/sqlite/db
SECRET_KEY=unique-secret-string
```

For development mode, we can execute `clustermgr-cli runserver`.
For production mode, it is recommended to use reliable WSGI server i.e. `gunicorn`.
Here's an example of how to use gunicorn to run Cluster Manager app.

```
pip install gunicorn
gunicorn -b 127.0.0.1:5000 clustermgr.application:app
```

By default, the app runs in development mode. To run it in production mode, simply pass environment variable
`APP_MODE=prod` to alter the mode.

```
gunicorn -b 127.0.0.1:5000 -e APP_MODE=prod clustermgr.application:app
```
