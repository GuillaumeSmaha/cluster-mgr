# Cluster Manager

GUI tool for managing Gluu Server OpenLDAP replication

## Installing Cluster Manager

### OS Packages

Install prerequisites packages first. On debian or ubuntu, install them using `apt-get`:

```
sudo apt-get install build-essential libssl-dev libffi-dev python-dev openjdk-7-jre-headless
```

### Java Libraries

Note, OpenJDK or any JVM is required as Cluster Manager relies on several Java libraries.
After prerequisites packages already installed, we need to get some Java JAR files and put them
in predefined data directory (by default the location is `$HOME/.clustermgr/javalibs` directory).

```
mkdir -p $HOME/.clustermgr/javalibs
wget http://ox.gluu.org/maven/org/xdi/oxauth-client/3.1.0-SNAPSHOT/oxauth-client-3.1.0-SNAPSHOT-jar-with-dependencies.jar -O $HOME/.clustermgr/javalibs/keygen.jar
```

### Python Libraries

Clone this repo or download the source manually.

```
cd /path/to/replication-mgr
python setup.py install
```

A successful installation will install a tool called `clustermgr-cli`.

## Running Cluster Manager

### Sync Database Schema

Run the tool to sync the database schema:

```
clustermgr-cli db upgrade
```

### App Configuration

Before running the app, we need to create custom config file to override default configuration.
Create a file at `$HOME/.clustermgr/instance/config.py`. Here's an example of custom `config.py`:

```
DEBUG=False
TESTING=False
SQLALCHEMY_DATABASE_URI=/path/to/sqlite/db  # example: sqlite:////opt/cluster-mgr/clustermgr.db
SECRET_KEY=unique-secret-string
```

### Running Server App

For development mode, we can execute `clustermgr-cli runserver`.
For production mode, it is recommended to use reliable WSGI server i.e. `gunicorn`.
Here's an example of how to use gunicorn to run Cluster Manager app.

```
pip install gunicorn
gunicorn -b 127.0.0.1:5000 clusterapp:app
```

By default, the app runs in development mode. To run it in production mode, simply pass environment variable
`APP_MODE=prod` to alter the mode.

```
gunicorn -b 127.0.0.1:5000 -e APP_MODE=prod clusterapp:app
```

### Running Background Task

All delayed tasks are executed in background.

```
APP_MODE=prod celery -A clusterapp.celery worker
```

To run periodic tasks:

```
APP_MODE=prod celery -A clusterapp.celery beat
```
