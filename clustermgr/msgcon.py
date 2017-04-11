import requests
import urlparse
import urllib


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
    def __init__(self, key, data):
        self.key = key
        self.embedded = data.get("_embedded", {})
        self.links = data.get("_links", {})
        self.page = data.get("page", {})

    def get_logs(self):
        if not self.has_logs():
            return []
        return [LogItem(item) for item in self.embedded[self.key]]

    def has_logs(self):
        if self.key not in self.embedded:
            return False
        return len(self.embedded[self.key]) > 0

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
    qs = urllib.urlencode({
        "sort": "id,desc",
        "page": page,
    })
    url = "{}/logger/api/oauth2-audit-logs/search/query?{}".format(
        base_url, qs,
    )
    req = requests.get(url)

    if not req.ok:
        return {}, req.status_code
    return req.json(), req.status_code


def get_server_logs(base_url, page=0, size=20):
    qs = urllib.urlencode({
        "sort": "id,desc",
        "page": page,
    })
    url = "{}/logger/api/oxauth-server-logs/search/query?{}".format(
        base_url, qs,
    )
    req = requests.get(url)

    if not req.ok:
        return {}, req.status_code
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
