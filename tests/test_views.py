import os
import unittest
import tempfile

import repmgr
from repmgr.models import LDAPServer


class ViewFunctionsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        repmgr.app.config.from_object('repmgr.config.TestingConfig')
        self.db_fd, repmgr.app.config['DATABASE'] = tempfile.mkstemp()
        repmgr.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
            repmgr.app.config['DATABASE']
        self.app = repmgr.app.test_client()
        with repmgr.app.app_context():
            repmgr.application.db.create_all()

    @classmethod
    def tearDownClass(self):
        os.close(self.db_fd)
        os.unlink(repmgr.app.config['DATABASE'])

    def test_01_add_server_adds_data_to_db(self):
        server_count = LDAPServer.query.count()
        self.app.post('/add_server/', data=dict(host='test.hostname.com',
                      port=1389, starttls=True, role='master', server_id=100,
                      replication_id=111), follow_redirects=True)
        self.assertEqual(server_count+1, LDAPServer.query.count())


if __name__ == '__main__':
    unittest.main()
