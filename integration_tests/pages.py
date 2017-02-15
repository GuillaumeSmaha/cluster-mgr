from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException

from locators import AddServerPageLocators as ASPL


class BasePage(object):
    def __init__(self, driver):
        self.driver = driver


class DashBoardPage(BasePage):
    """The Dashboard page that is visible once the app is loaded
    """
    pass


class AddServerPage(BasePage):
    """The page having the `Add Server` form"""
    def fill_details(self, host, port, startTLS, role, serverID, replID):
        """Fills the form using the input details.

        Args:
            host: hostname of the server
            port: port configured in the server
            startTLS (bool): Use startTLS or not
            role: `master` or `consumer`
            serverID: Integer ID value for the master
            replID: Interger ID value for the consumer
        """
        host_input = self.driver.find_element(*ASPL.HOST_INPUT)
        host_input.clear()
        host_input.send_keys(host)

        port_input = self.driver.find_element(*ASPL.PORT_INPUT)
        port_input.clear()
        port_input.send_keys(port)

        tls_checkbox = self.driver.find_element(*ASPL.STARTTLS_CHECK)
        if (startTLS and not tls_checkbox.get_attribute('checked')) or \
                (not startTLS and tls_checkbox.get_attribute('checked')):
            tls_checkbox.click()

        serverid_input = self.driver.find_element(*ASPL.SERVER_ID)
        serverid_input.clear()
        serverid_input.send_keys(serverID)

        repid_input = self.driver.find_element(*ASPL.REPLICATION_ID)
        repid_input.clear()
        repid_input.send_keys(replID)

    def add_master(self, host, port, startTLS, serverID):
        """Add a master server with the given details.

        Args:
            host: hostname of the server
            port: port configured in the server
            startTLS (bool): use startTLS or not
            serverID: numerical ID of the server
        """
        self.fill_details(host, port, startTLS, 'master', serverID, 0)
        self.driver.find_element(*ASPL.REPLICATION_ID).submit()
