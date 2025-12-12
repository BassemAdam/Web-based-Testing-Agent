from playwright.sync_api import Page
from .base_page import BasePage

class Page_0Page(BasePage):
    URL = "https://www.youtube.com"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._sign_in_button = page.get_by_role('link', name='Sign in')
        self._home_button = page.locator('a#endpoint.yt-simple-endpoint.style-scope.ytd-mini-guide-entry-renderer')
    
    def click_sign_in(self) -> None:
        """Clicks the 'Sign in' button to navigate to the sign-in page."""
        self._sign_in_button.click()
    
    def click_home(self) -> None:
        """Clicks the 'Home' button to navigate to the main YouTube home page."""
        self._home_button.click()