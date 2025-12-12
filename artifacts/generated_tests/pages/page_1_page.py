from playwright.sync_api import Page, Locator
from .base_page import BasePage

class Page_1Page(BasePage):
    URL = "Not specified"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._username_input = page.locator("best_locator_for_username")
        self._password_input = page.locator("best_locator_for_password")
        self._next_button = page.locator("best_locator_for_next_button")
    
    def click_next(self):
        """Click the 'Next' button to proceed with authentication."""
        self._next_button.click()
    
    def enter_invalid_credentials(self, email: str, password: str):
        """Enter invalid email and password on the sign-in form."""
        self._username_input.fill(email)
        self._password_input.fill(password)
    
    def enter_valid_credentials(self, email: str, password: str):
        """Enter valid email and password on the sign-in form."""
        self._username_input.fill(email)
        self._password_input.fill(password)
    
    def attempt_authentication(self):
        """Click 'Next' to attempt authentication."""
        self._next_button.click()