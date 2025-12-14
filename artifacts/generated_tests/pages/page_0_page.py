from playwright.sync_api import Page, Locator
from .base_page import BasePage

class Page_0Page(BasePage):
    URL = "https://example.com/"  # Updated URL as per feedback

    def __init__(self, page: Page):
        super().__init__(page)
        self._learn_more_link = page.get_by_role('link', name='Learn more')

    def navigate_to_domains(self) -> None:
        """
        Clicks the 'Learn more' link to navigate to the domains section of IANA.
        """
        self._learn_more_link.click()