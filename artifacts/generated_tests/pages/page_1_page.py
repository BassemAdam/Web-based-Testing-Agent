from playwright.sync_api import Page
from .base_page import BasePage

class Page_1Page(BasePage):
    URL = "Not specified"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._forgot_email_button = page.get_by_role('button', name='Forgot email?')
        self._next_button = page.get_by_role('button', name='Next')
    
    def click_forgot_email(self):
        """Click on 'Forgot email?' to initiate password reset."""
        self._forgot_email_button.click()
    
    def click_next_for_valid_credentials(self):
        """Click the 'Next' button to proceed with sign-in using a valid email and password."""
        self._next_button.click()
    
    def click_next_for_invalid_credentials(self, invalid_email: str = "invalid@example.com", invalid_password: str = "invalidpassword"):
        """Click the 'Next' button to attempt sign-in with an invalid email and password."""
        # Assuming there are input fields for email and password on this page
        self._page.fill('input[name="email"]', invalid_email)
        self._page.fill('input[name="password"]', invalid_password)
        self._next_button.click()