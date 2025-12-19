from .base_page import BasePage
from playwright.sync_api import Page, Locator


class Page_1Page(BasePage):
    URL = "https://automationexercise.com/products"

    def __init__(self, page: Page) -> None:
        self._page: Page = page
        self._polo_brand_link: Locator = page.locator("a[href=\"/brand_products/Polo\"]")
        self._view_product_link: Locator = page.locator("a[href=\"/product_details/1\"]")

    def click_polo_brand(self) -> None:
        """Click on the 'POLO' link under brand categories."""
        self._polo_brand_link.click()

    def assert_on_page(self) -> None:
        """Verify that the URL and page title match the expected values."""
        assert self._page.url == self.URL, f"Expected URL '{self.URL}', got '{self._page.url}'"
        assert self._page.title() == "Automation Exercise - All Products", (
            f"Expected title 'Automation Exercise - All Products', got '{self._page.title()}'"
        )

    def click_view_product(self) -> None:
        """Click on the 'View Product' link for a specific product."""
        self._view_product_link.click()