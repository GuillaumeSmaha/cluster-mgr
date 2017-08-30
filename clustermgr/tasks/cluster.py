from clustermgr.models import LDAPServer
from clustermgr.extensions import celery, wlogger
from clustermgr.core.remote import RemoteClient


@celery.task(bind=True)
def setup_provider(self, server_id, conffile):
    server = LDAPServer.query.get(server_id)
    tid = self.request.id
    p = RemoteClient(server.hostname)

    # TODO 
    # Finish with simpler way to run the setup procedures

