from selenium.webdriver.common.by import By


class AddServerPageLocators(object):
    """Class hodling the locators for the Add Server Page"""
    HOST_INPUT = (By.ID, 'host')
    PORT_INPUT = (By.ID, 'port')
    STARTTLS_CHECK = (By.ID, 'starttls')
    SERVER_ID = (By.ID, 'server_id')
    REPLICATION_ID = (By.ID, 'replication_id')
