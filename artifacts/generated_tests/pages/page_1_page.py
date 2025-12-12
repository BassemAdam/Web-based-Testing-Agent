from playwright.sync_api import Page
from .base_page import BasePage

class Page_1Page(BasePage):
    URL = "Not specified"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._username_input = page.locator("input[name='username']")  # Replace with actual locator
        self._password_input = page.locator("input[name='password']")  # Replace with actual locator
        self._next_button = page.get_by_role("button", name="Next")  # Replace with actual locator
    
    def enter_invalid_credentials(self):
        self._username_input.fill("invalid@example.com")
        self._password_input.fill("invalidpassword")
    
    def enter_valid_credentials(self, username: str, password: str):
        self._username_input.fill(username)
        self._password_input.fill(password)
    
    def click_next(self):
        self._next_button.click()