from playwright.sync_api import Page
from .base_page import BasePage

class Page_0Page(BasePage):
    URL = "Not specified"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._sign_in_button = page.get_by_role('link', name='Sign in')
    
    def click_sign_in(self):
        """Clicks the 'Sign in' button."""
        self._sign_in_button.click()