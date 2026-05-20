import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_example_click_link_executes_04(page: Page):
    import traceback
    try:
        # Test identifiers and start URL
        test_id = "tc_example_click_link_executes_04"
        start_url = "https://example.com"

        # Step 1: Navigate to the Example Domain page
        page.goto(start_url)
        # Screenshot immediately after navigation (required)
        page.screenshot(path=f"screenshots/{test_id}/01_initial_page.png")

        # Step 2: Assert the "Learn more" link is present and correct
        # Use the provided locator exactly
        learn_more_link = page.get_by_role('link', name='Learn more')
        # Assert the link is visible
        expect(learn_more_link).to_be_visible()
        # Assert the href attribute matches the expected target
        expect(learn_more_link).to_have_attribute("href", "https://iana.org/domains/example")
        # Screenshot after assertion
        page.screenshot(path=f"screenshots/{test_id}/02_after_assert_link_visible.png")

        # Step 3: Wait to ensure clickable elements are ready
        # Wait for the link to be visible (clickable)
        learn_more_link.wait_for(state="visible", timeout=5000)
        page.screenshot(path=f"screenshots/{test_id}/03_after_wait.png")

        # Step 4: Click the "Learn more" link to verify it is interactable
        # Perform the click. The link may or may not navigate the current page;
        # do not assume destination - just ensure the click executes without error.
        learn_more_link.click()
        # Optionally wait briefly for any navigation/load to complete; ignore timeouts
        try:
            page.wait_for_load_state("load", timeout=5000)
        except Exception:
            # It's acceptable if no navigation occurred or load did not complete within timeout
            pass
        page.screenshot(path=f"screenshots/{test_id}/04_after_click.png")

        # Step 5: Final assertion - ensure we can still interact / recover to the start page.
        # To be robust regardless of whether the click navigated away, navigate back to the start page
        # and confirm the link is present again. This verifies the test harness can proceed and the click
        # did not produce an unhandled error.
        page.goto(start_url)
        page.screenshot(path=f"screenshots/{test_id}/05_after_navigate_back.png")

        # Re-locate the link and assert it's visible again
        learn_more_link_after = page.get_by_role('link', name='Learn more')
        expect(learn_more_link_after).to_be_visible()
        expect(learn_more_link_after).to_have_attribute("href", "https://iana.org/domains/example")
        page.screenshot(path=f"screenshots/{test_id}/06_after_final_assert.png")

    except Exception as e:
        print(f"ERROR in test_tc_example_click_link_executes_04: {e}")
        traceback.print_exc()
        # Take error screenshot before re-raising
        try:
            page.screenshot(path="screenshots/tc_example_click_link_executes_04/error.png")
        except Exception:
            # If taking a screenshot also fails, print a note and continue to raise original exception
            print("Failed to capture error screenshot.")
        raise