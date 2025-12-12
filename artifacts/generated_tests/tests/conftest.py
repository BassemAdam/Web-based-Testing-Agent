import pytest
from playwright.sync_api import sync_playwright, Page, Locator
from pathlib import Path

# --- Monkey Patching for Automatic Screenshots ---
# This ensures screenshots are taken for EVERY action (click, fill, goto)
# regardless of how the test is written (BasePage or raw Playwright)

def _capture_screenshot(page, name, wait_for_load=False):
    """Helper to capture screenshot if configured."""
    if hasattr(page, 'screenshot_dir') and hasattr(page, 'screenshot_counter'):
        # Wait for page to stabilize before capturing
        try:
            if wait_for_load:
                # Wait for navigation to complete (for goto, clicks that navigate)
                # Use domcontentloaded instead of networkidle for complex sites like YouTube
                page.wait_for_load_state('domcontentloaded', timeout=3000)
                # Additional small wait for dynamic content
                page.wait_for_timeout(1000)
            else:
                # Small wait for dynamic content to render (for regular actions)
                page.wait_for_timeout(500)
        except Exception as e:
            print(f"[Screenshot] Wait timeout (proceeding anyway): {e}")
        
        page.screenshot_counter += 1
        # Clean filename
        clean_name = str(name).replace(':', '_').replace('/', '_').replace('\\', '_').replace('"', '').replace("'", "")[:50]
        path = page.screenshot_dir / f"{page.screenshot_counter:02d}_{clean_name}.png"
        try:
            page.screenshot(path=str(path))
            print(f"[Screenshot] Captured: {path.name}")
        except Exception as e:
            print(f"[Screenshot] Failed to capture: {e}")

# Save original methods to avoid recursion
if not getattr(Locator, '_is_patched', False):
    _original_locator_click = Locator.click
    _original_locator_fill = Locator.fill
    _original_page_goto = Page.goto
    _original_page_click = Page.click
    _original_page_fill = Page.fill

    def _patched_locator_click(self, *args, **kwargs):
        result = _original_locator_click(self, *args, **kwargs)
        # Click might trigger navigation, wait for page to load
        _capture_screenshot(self.page, f"click_{self}", wait_for_load=True)
        return result

    def _patched_locator_fill(self, value, *args, **kwargs):
        result = _original_locator_fill(self, value, *args, **kwargs)
        # Fill doesn't navigate, just wait briefly
        _capture_screenshot(self.page, f"fill_{self}", wait_for_load=False)
        return result

    def _patched_page_goto(self, url, *args, **kwargs):
        result = _original_page_goto(self, url, *args, **kwargs)
        # Goto always navigates, wait for page to load
        _capture_screenshot(self, "navigate", wait_for_load=True)
        return result
        
    def _patched_page_click(self, selector, *args, **kwargs):
        result = _original_page_click(self, selector, *args, **kwargs)
        # Click might trigger navigation, wait for page to load
        _capture_screenshot(self, f"click_{selector}", wait_for_load=True)
        return result

    def _patched_page_fill(self, selector, value, *args, **kwargs):
        result = _original_page_fill(self, selector, value, *args, **kwargs)
        # Fill doesn't navigate, just wait briefly
        _capture_screenshot(self, f"fill_{selector}", wait_for_load=False)
        return result

    # Apply patches
    Locator.click = _patched_locator_click
    Locator.fill = _patched_locator_fill
    Page.goto = _patched_page_goto
    Page.click = _patched_page_click
    Page.fill = _patched_page_fill
    
    # Mark as patched
    Locator._is_patched = True
    Page._is_patched = True


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {
            "width": 1280,
            "height": 720,
        }
    }

@pytest.fixture(scope="function")
def page(browser, request):
    """Provides a Playwright page with screenshot support."""
    context = browser.new_context()
    page = context.new_page()
    
    # Add screenshot directory path to page object
    # Use request.node.name to get the test name reliably
    test_name = request.node.name
    
    # Strip parametrization (e.g., [chromium]) to match test_runner expectation
    if "[" in test_name:
        test_name = test_name.split("[")[0]
        
    # Sanitize filename (remove special chars)
    test_name = "".join(x for x in test_name if x.isalnum() or x in "_-")
    
    screenshot_dir = Path(__file__).parent.parent / "screenshots" / test_name
    
    # Clean up old screenshots for this test if they exist
    if screenshot_dir.exists():
        import shutil
        shutil.rmtree(screenshot_dir)
        
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    page.screenshot_dir = screenshot_dir
    page.screenshot_counter = 0
    
    print(f"[DEBUG] Screenshot directory: {screenshot_dir}")
    
    yield page
    
    context.close()
