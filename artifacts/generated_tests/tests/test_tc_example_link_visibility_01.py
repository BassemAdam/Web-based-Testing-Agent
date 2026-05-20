import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_example_link_visibility_01(page):
    try:
        # Step 1: Navigate to the Example Domain start URL
        page.goto("https://example.com")
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_example_link_visibility_01/01_initial_page.png")
        
        # Step 2: Confirm the page URL is the expected start URL
        from playwright.sync_api import expect
        expect(page).to_have_url("https://example.com/")
        # Screenshot after URL assertion
        page.screenshot(path="screenshots/tc_example_link_visibility_01/02_after_assert_page_loaded.png")
        
        # Step 3: Locate the 'Learn more' link using the provided locator
        learn_more_link = page.get_by_role('link', name='Learn more')
        # Screenshot after locating element (state capture)
        page.screenshot(path="screenshots/tc_example_link_visibility_01/03_after_locating_link.png")
        
        # Step 4: Verify the 'Learn more' link is visible on the page
        expect(learn_more_link).to_be_visible()
        # Screenshot after visibility assertion
        page.screenshot(path="screenshots/tc_example_link_visibility_01/04_after_assert_link_visible.png")
        
        # Step 5: Verify the visible text of the link equals 'Learn more'
        expect(learn_more_link).to_have_text("Learn more")
        # Screenshot after text assertion
        page.screenshot(path="screenshots/tc_example_link_visibility_01/05_after_assert_link_text.png")
        
        # Step 6: Short wait to allow DOM to be stable (per test steps)
        page.wait_for_timeout(500)
        # Screenshot after wait
        page.screenshot(path="screenshots/tc_example_link_visibility_01/06_after_wait.png")
        
        # Final sanity check: link still visible
        expect(learn_more_link).to_be_visible()
        page.screenshot(path="screenshots/tc_example_link_visibility_01/07_final.png")
        
    except Exception as e:
        print(f"ERROR in test_tc_example_link_visibility_01: {e}")
        import traceback
        traceback.print_exc()
        # Capture error state screenshot before re-raising
        page.screenshot(path="screenshots/tc_example_link_visibility_01/error.png")
        raise