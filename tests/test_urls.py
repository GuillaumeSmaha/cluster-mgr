import os
import unittest
import tempfile

import clustermgr


class UrlsTestCase(unittest.TestCase):
    def setUp(self):
        clustermgr.app.config.from_object('clustermgr.config.TestingConfig')
        self.db_fd, clustermgr.app.config['DATABASE'] = tempfile.mkstemp()
        clustermgr.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + \
            clustermgr.app.config['DATABASE']
        self.app = clustermgr.app.test_client()
        with clustermgr.app.app_context():
            clustermgr.application.db.create_all()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(clustermgr.app.config['DATABASE'])

    def test_01_homepage(self):
        resp = self.app.get('/')
        self.assertIn('h2', resp.data)

if __name__ == '__main__':
    unittest.main()
