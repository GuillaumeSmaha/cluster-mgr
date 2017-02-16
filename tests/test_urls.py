import os
import unittest
import tempfile

import repmgr
from repmgr.application import db
from repmgr.models import LDAPServer


class UrlsTestCase(unittest.TestCase):
    def setUp(self):
        repmgr.app.config.from_object('repmgr.config.TestingConfig')
        self.db_fd, repmgr.app.config['DATABASE'] = tempfile.mkstemp()
        repmgr.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
            repmgr.app.config['DATABASE']
        self.app = repmgr.app.test_client()
        with repmgr.app.app_context():
            repmgr.application.db.create_all()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(repmgr.app.config['DATABASE'])

    def test_01_homepage(self):
        resp = self.app.get('/')
        self.assertIn('h1', resp.data)

    def test_02_add_server_page(self):
        page = self.app.get('/add_server/')
        self.assertIn('<h1 class="page-header">New Server</h1>', page.data)

if __name__ == '__main__':
    unittest.main()
