from playwright.sync_api import Page
from pathlib import Path


class BasePage:
    """Base class for all Page Objects."""

    # Override this in subclasses if the page has a specific URL
    URL = None

    def __init__(self, page: Page):
        self.page = page
    
    def capture_screenshot(self, step_name: str):
        """Capture a screenshot for the current step."""
        try:
            if hasattr(self.page, 'screenshot_dir') and hasattr(self.page, 'screenshot_counter'):
                self.page.screenshot_counter += 1
                # Clean step name for filename
                clean_name = step_name.replace(':', '_').replace('/', '_').replace('\\', '_')[:50]
                screenshot_path = self.page.screenshot_dir / f"{self.page.screenshot_counter:02d}_{clean_name}.png"
                self.page.screenshot(path=str(screenshot_path))
                return str(screenshot_path)
        except Exception as e:
            print(f"Warning: Could not capture screenshot: {e}")
        return None

    def navigate(self, url: str | None = None):
        """Navigate to a URL. Uses self.URL if no url is provided."""
        target_url = url or self.URL
        if target_url:
            self.page.goto(target_url)
            self.capture_screenshot("navigate")
    
    def click(self, selector: str):
        """Click an element and capture screenshot."""
        self.page.click(selector)
        self.capture_screenshot(f"click_{selector[:30]}")
    
    def fill(self, selector: str, value: str):
        """Fill an input field and capture screenshot."""
        self.page.fill(selector, value)
        self.capture_screenshot(f"fill_{selector[:30]}")
    
    def wait_for_selector(self, selector: str, timeout: int = 30000):
        """Wait for selector and capture screenshot."""
        self.page.wait_for_selector(selector, timeout=timeout)
        self.capture_screenshot(f"wait_{selector[:30]}")

    def get_title(self) -> str:
        return self.page.title()
