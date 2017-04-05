# Replication Manager

GUI tool for managing Gluu Server OpenLDAP replication

## Installing Replication Manager

Install prerequisites packages first. On debian or ubuntu, install them using `apt-get`:

```
sudo apt-get install build-essential libssl-dev libffi-dev python-dev
```

Clone this repo or download the source manually.

```
cd /path/to/replication-mgr
python setup.py install
```

## Running Replication Manager

A successful installation will install a tool called `repmgr-cli`.
Run the tool to initialize the database schema:

```
repmgr-cli db upgrade
```

For development mode, we can execute `repmgr-cli runserver`.
For production mode, it is recommended to use reliable WSGI server i.e. `gunicorn`.
Here's an example of how to use gunicorn to run replication manager app.

```
pip install gunicorn
gunicorn -b :5000 repmgr.application:app
```
