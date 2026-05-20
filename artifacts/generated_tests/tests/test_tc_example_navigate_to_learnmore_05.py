import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_example_navigate_to_learnmore_05(page):
    try:
        # Start URL
        start_url = "https://example.com"
        expected_link_href = "https://iana.org/domains/example"

        # Step 1: Navigate to the start URL (Example Domain)
        page.goto(start_url)
        # Screenshot immediately after navigation (required)
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/01_initial_page.png")

        # Step 2: Assert the "Learn more" link is present and visible, and has the expected href
        learn_more_link = page.get_by_role("link", name="Learn more")
        # Assert visibility
        from playwright.sync_api import expect
        expect(learn_more_link).to_be_visible()
        # Read and assert href attribute
        href_value = learn_more_link.get_attribute("href")
        assert href_value == expected_link_href, f"Link href was '{href_value}', expected '{expected_link_href}'"
        # Screenshot after this assertion
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/02_after_initial_assert.png")

        # Step 3: Repeat confirmation that the page is loaded and the link is present (as per test steps)
        expect(learn_more_link).to_be_visible()
        href_value_again = learn_more_link.get_attribute("href")
        assert href_value_again == expected_link_href, "Second check: href does not match expected"
        # Screenshot after second confirmation
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/03_after_confirm_assert.png")

        # Step 4: Wait to stabilize DOM before reading href
        page.wait_for_timeout(500)  # short stabilization wait
        # Screenshot after wait
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/04_after_wait.png")

        # Step 5: Double-check target URL to navigate to
        # Re-fetch locator in case of any minor DOM changes
        learn_more_link_refreshed = page.get_by_role("link", name="Learn more")
        expect(learn_more_link_refreshed).to_be_visible()
        href_final_check = learn_more_link_refreshed.get_attribute("href")
        assert href_final_check == expected_link_href, "Final href check failed"
        # Screenshot after double-check
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/05_after_doublecheck_assert.png")

        # Step 6: Explicitly navigate to the link's destination using a direct navigate action
        page.goto(href_final_check)
        # Screenshot after navigating to the destination
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/06_after_explicit_navigate.png")

        # Step 7: Confirm the original Example Domain page is loaded again.
        # The test case requires confirming example.com is loaded; navigate back explicitly and verify.
        page.goto(start_url)
        # Screenshot after navigating back to the start page
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/07_after_navigate_back.png")

        # Final assertion: the "Learn more" link should be present on the Example Domain page
        final_link = page.get_by_role("link", name="Learn more")
        expect(final_link).to_be_visible()
        assert final_link.get_attribute("href") == expected_link_href, "Final assertion: link href mismatch on returned page"
        # Final screenshot after the assertion
        page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/08_after_final_assert.png")

    except Exception as e:
        # Error handling: print traceback, take an error screenshot, then re-raise
        print(f"ERROR in test_tc_example_navigate_to_learnmore_05: {e}")
        import traceback
        traceback.print_exc()
        try:
            page.screenshot(path="screenshots/tc_example_navigate_to_learnmore_05/error.png")
        except Exception:
            # If screenshot fails in the except block, still raise the original exception
            print("Failed to take error screenshot.")
        raise