import unittest

from selenium import webdriver

from pages import AddServerPage, Dashboard
from config import url


class AddServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.browser = webdriver.Firefox()
        cls.browser.implicitly_wait(3)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()

    def test_01_add_new_master(self):
        page_url = url + '/add_server/'
        # User opens the Add server Page
        self.browser.get(page_url)
        # Enter the details of the server and submit
        asp = AddServerPage(self.browser)
        asp.add_master('provider.example.com', '1389', True, 100)
        # User is redirected to the dashboard with a success message
        dash = Dashboard(self.browser)

        # User see thes added server listed in the homepage
        self.assertTrue(dash.is_server_listed('provider.example.com', 100))


if __name__ == '__main__':
    unittest.main()
