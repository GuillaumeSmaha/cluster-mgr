import os
import unittest
import tempfile

import clustermgr
from clustermgr.models import LDAPServer


class ViewFunctionsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        clustermgr.app.config.from_object('clustermgr.config.TestingConfig')
        self.db_fd, clustermgr.app.config['DATABASE'] = tempfile.mkstemp()
        clustermgr.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
            clustermgr.app.config['DATABASE']
        self.app = clustermgr.app.test_client()
        with clustermgr.app.app_context():
            clustermgr.application.db.create_all()

    @classmethod
    def tearDownClass(self):
        os.close(self.db_fd)
        os.unlink(clustermgr.app.config['DATABASE'])

    def xtest_01_add_server_adds_data_to_db(self):
        server_count = LDAPServer.query.count()
        self.app.post('/add_server/', data=dict(host='test.hostname.com',
                      port=1389, starttls=True, role='master', server_id=100,
                      replication_id=111), follow_redirects=True)
        self.assertEqual(server_count+1, LDAPServer.query.count())


if __name__ == '__main__':
    unittest.main()
