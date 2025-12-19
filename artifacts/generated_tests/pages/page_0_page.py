from playwright.sync_api import Page, Locator
from .base_page import BasePage

class Page_0Page(BasePage):
    URL = "https://automationexercise.com/"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.page: Page = page
        self._products_link = page.locator("a[href=\"/products\"]")
        self._cart_link = page.locator("a[href=\"/view_cart\"]")
        self._signup_login_link = page.locator("a[href=\"/login\"]")
        self._api_testing_link = page.locator("a[href=\"/api_list\"]")

    def open(self) -> None:
        """Navigate to the page URL."""
        self.page.goto(self.URL)

    def click_cart(self) -> None:
        """Click on the 'Cart' link."""
        self._cart_link.click()

    def click_signup_login(self) -> None:
        """Click on the 'Signup / Login' link."""
        self._signup_login_link.click()

    def click_api_testing(self) -> None:
        """Click on the 'API Testing' link."""
        self._api_testing_link.click()

    def click_products(self) -> None:
        """Click on the 'Products' link."""
        self._products_link.click()