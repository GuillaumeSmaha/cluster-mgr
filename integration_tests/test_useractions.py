import unittest

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
        try:
            WebDriverWait(self.browser, 10).until(
                    EC.presence_of_element_located((By.ID, "servers"))
            )
        finally:
            # User is redirected to the dashboard with a success message
            dash = Dashboard(self.browser)
            # User see thes added server listed in the homepage
            self.assertTrue(dash.is_server_listed('provider.example.com', 100))


if __name__ == '__main__':
    unittest.main()
