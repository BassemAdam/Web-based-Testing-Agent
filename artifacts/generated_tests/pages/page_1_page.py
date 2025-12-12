from playwright.sync_api import Page, Locator
from .base_page import BasePage

class Page_1Page(BasePage):
    URL = "Not specified"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._next_button: Locator = page.get_by_role("button", name="Next")
        self._username_input: Locator = page.locator("#usernameInput")
    
    def click_next(self):
        """Click the 'Next' button to proceed with authentication."""
        self._next_button.click()
    
    def enter_invalid_credentials(self, username: str = "invalid@example.com", password: str = "invalidpassword"):
        """Enter invalid email/username and password on the sign-in form."""
        self._username_input.fill(username)
        # Assuming there's a locator for password input as well
        page.locator("#passwordInput").fill(password)
    
    def enter_valid_credentials(self, username: str = "valid@example.com", password: str = "validpassword"):
        """Enter valid email/username and password on the sign-in form."""
        self._username_input.fill(username)
        # Assuming there's a locator for password input as well
        page.locator("#passwordInput").fill(password)
    
    def click_next_with_invalid_credentials(self):
        """Click 'Next' to attempt authentication with invalid credentials."""
        self._next_button.click()