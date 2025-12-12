from playwright.sync_api import Page
from .base_page import BasePage

class Page_0Page(BasePage):
    URL = "https://www.youtube.com/"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._home_button = page.locator('a#endpoint.yt-simple-endpoint.style-scope.ytd-mini-guide-entry-renderer')
        self._signin_button = page.get_by_role('link', name='Sign in')
    
    def navigate_to_home(self) -> None:
        """Navigate back to the main YouTube home page."""
        self._home_button.click()
    
    def navigate_to_signin(self) -> None:
        """Navigate to the sign-in page by clicking the 'Sign in' button."""
        self._signin_button.click()