from playwright.sync_api import Page
from .base_page import BasePage

class Page_0Page(BasePage):
    URL = "https://automationexercise.com/"

    def __init__(self, page: Page):
        super().__init__(page)
        self._home_link = page.locator("a:has-text(\"Home\")").nth(0)
        self._products_link = page.locator("a[href=\"/products\"]").nth(0)
        self._cart_link = page.locator("a[href=\"/view_cart\"]").nth(0)
        self._signup_login_link = page.locator("a[href=\"/login\"]").nth(0)
        self._test_cases_link = page.locator("a[href=\"/test_cases\"]").nth(0)
        self._api_testing_link = page.locator("a[href=\"/api_list\"]").nth(0)
        self._video_tutorials_link = page.locator("a[href=\"https://www.youtube.com/c/AutomationExercise\"]").nth(0)

    def click_home(self) -> None:
        """Click on the 'Home' link."""
        self._home_link.click()

    def click_products(self) -> None:
        """Click on the 'Products' link."""
        self._products_link.click()

    def click_cart(self) -> None:
        """Click on the 'Cart' link."""
        self._cart_link.click()

    def click_signup_login(self) -> None:
        """Click on the 'Signup / Login' link."""
        self._signup_login_link.click()

    def click_test_cases(self) -> None:
        """Click on the 'Test Cases' link."""
        self._test_cases_link.click()

    def click_api_testing(self) -> None:
        """Click on the 'API Testing' link."""
        self._api_testing_link.click()

    def click_video_tutorials(self) -> None:
        """Click on the 'Video Tutorials' link."""
        self._video_tutorials_link.click()