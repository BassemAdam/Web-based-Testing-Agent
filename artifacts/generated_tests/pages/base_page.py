from playwright.sync_api import Page


class BasePage:
    """Base class for all Page Objects."""

    # Override this in subclasses if the page has a specific URL
    URL = None

    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str | None = None):
        """Navigate to a URL. Uses self.URL if no url is provided."""
        target_url = url or self.URL
        if target_url:
            self.page.goto(target_url)

    def get_title(self) -> str:
        return self.page.title()
