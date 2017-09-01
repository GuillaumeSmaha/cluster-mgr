from clustermgr.models import LDAPServer
from clustermgr.extensions import celery, wlogger
from clustermgr.core.remote import RemoteClient


@celery.task(bind=True)
def setup_provider(self, server_id, conffile):
    server = LDAPServer.query.get(server_id)
    tid = self.request.id
    c = RemoteClient(server.hostname)
    try:
        c.startup()
    except Exception as e:
        wlogger.log(tid, "Cannot establish SSH connection {0}".format(e),
                    "error")
        return False
