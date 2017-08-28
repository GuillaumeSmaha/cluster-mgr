"""A Flask blueprint with the views and the business logic dealing with
the logging server managed in the cluster-manager
"""
import requests

from flask import Blueprint, render_template, redirect, request

from clustermgr.extensions import db
from clustermgr.models import LoggingServer
from clustermgr.forms import LoggingServerForm
from clustermgr.core.msgcon import get_audit_logs, get_server_logs, \
    get_server_log_item, get_audit_log_item, LogCollection, LogItem

logserver = Blueprint('logserver', __name__, template_folder='templates')


@logserver.route("/", methods=["GET", "POST"])
def logging_server():
    log = LoggingServer.query.first()
    form = LoggingServerForm()

    if request.method == "GET" and log is not None:
        form.url.data = log.url

    if form.validate_on_submit():
        if not log:
            log = LoggingServer()
        log.url = form.url.data
        db.session.add(log)
        db.session.commit()
        return redirect("logging_server")
    return render_template("logging_server.html", log=log, form=form)


@logserver.route("/server-log")
def oxauth_server_log():
    err = ""
    logs = None
    server = LoggingServer.query.first()
    page = request.args.get("page", 0)

    if not server:
        err = "Missing logging server configuration."
        return render_template("oxauth_server_log.html", logs=logs, err=err)

    try:
        data, status_code = get_server_logs(server.url, page)
        logs = LogCollection("oxauth-server-logs", data)
        if not logs.has_logs():
            err = "Logs are not available at the moment. Please try again."
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("oxauth_server_log.html", logs=logs, err=err)


@logserver.route("/audit-log")
def oxauth_audit_log():
    err = ""
    logs = None
    server = LoggingServer.query.first()
    page = request.args.get("page", 0)

    if not server:
        err = "Missing logging server configuration."
        return render_template("oxauth_audit_log.html", logs=logs, err=err)

    try:
        data, status_code = get_audit_logs(server.url, page)
        logs = LogCollection("oauth2-audit-logs", data)
        if not logs.has_logs():
            err = "Logs are not available at the moment. Please try again."
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("oxauth_audit_log.html", logs=logs, err=err)


@logserver.route("/audit_log/<int:id>")
def audit_log_item(id):
    err = ""
    log = None
    server = LoggingServer.query.first()

    if not server:
        err = "Missing logging server configuration."
        return render_template("view_audit_log.html", log=log, err=err)

    try:
        data, status_code = get_audit_log_item(server.url, id)
        if not data:
            err = "Log is not available at the momment. Please try again."
        else:
            log = LogItem(data)
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("view_audit_log.html", log=log, err=err)


@logserver.route("/server_log/<int:id>")
def server_log_item(id):
    err = ""
    log = None
    server = LoggingServer.query.first()

    if not server:
        err = "Missing logging server configuration."
        return render_template("view_server_log.html", log=log, err=err)

    try:
        data, status_code = get_server_log_item(server.url, id)
        if not data:
            err = "Log is not available at the momment. Please try again."
        else:
            log = LogItem(data)
    except requests.exceptions.ConnectionError:
        err = "Unable to establish connection to logging server. " \
              "Please check the connection URL."
    return render_template("view_server_log.html", log=log, err=err)
