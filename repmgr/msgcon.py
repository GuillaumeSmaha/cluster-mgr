import requests
import urlparse


class LogItem(object):
    def __init__(self, data):
        self.data = data

    @property
    def id(self):
        url = self.data["_links"]["self"]["href"]
        return int(url.rsplit("/", 1)[-1])

    def __getattr__(self, name):
        return self.data.get(name)


class LogCollection(object):
    def __init__(self, embedded, links, page):
        self.embedded = embedded
        self.links = links
        self.page = page

    def get_logs(self, key):
        if key not in self.embedded:
            return []
        return [LogItem(item) for item in self.embedded[key]]

    @property
    def has_next(self):
        return "next" in self.links

    @property
    def next_page(self):
        if not self.has_next:
            return 0
        return self._get_page(self.links["next"]["href"])

    @property
    def has_prev(self):
        return "prev" in self.links

    @property
    def prev_page(self):
        if not self.has_prev:
            return 0
        return self._get_page(self.links["prev"]["href"])

    def _get_page(self, url):
        parsed_url = urlparse.urlparse(url)
        parsed_qs = urlparse.parse_qs(parsed_url.query)
        try:
            page = parsed_qs["page"][0]
        except (KeyError, IndexError,):
            page = 0
        return page


def get_audit_logs(base_url, page=0, size=20):
    url = "{}/logger/api/oauth2-audit-logs".format(base_url)
    req = requests.get(url)

    if not req.ok:
        return [], req.status_code
    return req.json(), req.status_code


def get_server_logs(base_url, page=0, size=20):
    url = "{}/logger/api/oxauth-server-logs?page".format(base_url)
    req = requests.get(url)

    if not req.ok:
        return [], req.status_code
    return req.json(), req.status_code


def get_audit_log_item(base_url, id):
    url = "{}/logger/api/oauth2-audit-logs/{}".format(base_url, id)
    req = requests.get(url)

    if not req.ok:
        return {}, req.status_code
    return req.json(), req.status_code


def get_server_log_item(base_url, id):
    url = "{}/logger/api/oxauth-server-logs/{}".format(base_url, id)
    req = requests.get(url)

    if not req.ok:
        return {}, req.status_code
    return req.json(), req.status_code


# TODO: remove dummies below

audit_logs = LogCollection(
    embedded={
        "oauth2-audit-logs": [{
            "ip": "10.0.2.2",
            "action": "USER_AUTHORIZATION",
            "clientId": "@!7A06.6C73.B7D4.3983!0001!CFEA.2908!0008!13E4.C749",  # noqa
            "username": "admin",
            "scope": "openid profile email user_name",
            "success": True,
            "timestamp": "2016-10-03T12:53:47.509+0000",
            "_links": {
                "self": {
                    "href": "http://localhost:8080/api/oauth2-audit-logs/3335"  # noqa
                },
                "oAuth2AuditLoggingEvent": {
                    "href": "http://localhost:8080/api/oauth2-audit-logs/3335"  # noqa
                },
            },
        }]
    },
    links={
        "first": {
            "href": "http://localhost:8080/api/oauth2-audit-logs/search/query?ip=10.0.2.2&username=admin&scope=openid&page=0&size=1"  # noqa
        },
        "self": {
            "href": "http://localhost:8080/api/oauth2-audit-logs/search/query?ip=10.0.2.2&username=admin&scope=openid&size=1"  # noqa
        },
        "next": {
            "href": "http://localhost:8080/api/oauth2-audit-logs/search/query?ip=10.0.2.2&username=admin&scope=openid&page=1&size=1"  # noqa
        },
        "last": {
            "href": "http://localhost:8080/api/oauth2-audit-logs/search/query?ip=10.0.2.2&username=admin&scope=openid&page=1&size=1"  # noqa
        },
    },
    page={
        "size": 1,
        "totalElements": 2,
        "totalPages": 2,
        "number": 0,
    }
)

server_logs = LogCollection(
    embedded={
        "oxauth-server-logs": [{
            "timestamp": "2017-01-14T18:48:17.000+0000",
            "formattedMessage": "Start U2F request clean up",
            "loggerName": "org.xdi.oxauth.service.CleanerTimer",
            "level": "DEBUG",
            "exceptions": [],
            "_links": {
                "self": {
                    "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs/4"  # noqa
                },
                "oXAuthServerLoggingEvent": {
                    "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs/4"  # noqa
                }
            }
        }],
    },
    links={
        "first": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs?page=0&size=1",  # noqa
        },
        "prev": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs?page=2&size=1",  # noqa
        },
        "self": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs"
        },
        "next": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs?page=4&size=1",  # noqa
        },
        "last": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs?page=486&size=1"  # noqa
        },
        "profile": {
            "href": "http://127.0.0.1:9339/logger/api/profile/oxauth-server-logs"  # noqa
        },
        "search": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs/search"  # noqa
        }
    },
    page={
        "size": 1,
        "totalElements": 487,
        "totalPages": 487,
        "number": 3
    }
)

dummy_server_log = LogItem({
    "timestamp": "2017-01-14T18:48:17.000+0000",
    "formattedMessage": "Start U2F request clean up",
    "loggerName": "org.xdi.oxauth.service.CleanerTimer",
    "level": "DEBUG",
    "exceptions": [],
    "_links": {
        "self": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs/4"
        },
        "oXAuthServerLoggingEvent": {
            "href": "http://127.0.0.1:9339/logger/api/oxauth-server-logs/4"
        }
    }
})


dummy_audit_log = LogItem({
    "ip": "10.0.2.2",
    "action": "USER_AUTHORIZATION",
    "clientId": "@!00EA.DF1E.31A5.C287!0001!50C2.44A6!0008!DF32.8FD8",
    "macAddress": "08-00-27-36-17-42",
    "username": None,
    "scope": "openid profile email user_name",
    "success": False,
    "timestamp": "2017-01-14T19:17:49.000+0000",
    "_links": {
        "self": {
            "href": "http://127.0.0.1:9339/logger/api/oauth2-audit-logs/1"
        },
        "oAuth2AuditLoggingEvent": {
            "href": "http://127.0.0.1:9339/logger/api/oauth2-audit-logs/1"
        }
    }
})
