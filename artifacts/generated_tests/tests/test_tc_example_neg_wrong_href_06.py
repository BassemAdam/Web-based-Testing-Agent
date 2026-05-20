import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_example_neg_wrong_href_06(page: Page):
    import traceback
    try:
        # Step 1: Navigate to the start URL
        page.goto("https://example.com")
        # Screenshot immediately after navigation (requirement)
        page.screenshot(path="screenshots/tc_example_neg_wrong_href_06/01_initial_page.png")

        # Step 1 (assert): Confirm the "Learn more" link is present and visible
        learn_more_link = page.get_by_role('link', name='Learn more')
        expect(learn_more_link).to_be_visible()
        # Screenshot after the first assert
        page.screenshot(path="screenshots/tc_example_neg_wrong_href_06/02_after_first_assert.png")

        # Step 2 (navigate): Re-open Example Domain to follow the test steps explicitly
        page.goto("https://example.com")
        # Screenshot after navigation action
        page.screenshot(path="screenshots/tc_example_neg_wrong_href_06/03_after_navigate.png")

        # Step 3 (assert): Confirm the link has the expected correct href
        expect(learn_more_link).to_have_attribute("href", "https://iana.org/domains/example")
        # Screenshot after the second assert
        page.screenshot(path="screenshots/tc_example_neg_wrong_href_06/04_after_second_assert.png")

        # Step 4 (wait): Stabilize before final assertion
        page.wait_for_timeout(1000)  # wait 1 second
        # Screenshot after wait
        page.screenshot(path="screenshots/tc_example_neg_wrong_href_06/05_after_wait.png")

        # Step 5 (negative assert): Ensure the link does NOT point to an incorrect internal URL
        href_value = learn_more_link.get_attribute("href")
        # Use expect to verify the correct href (positive check) and also assert explicitly the negative condition
        expect(learn_more_link).to_have_attribute("href", "https://iana.org/domains/example")
        wrong_href = "https://example.com/wrong"
        assert href_value != wrong_href, f"Link href unexpectedly equals wrong URL: {wrong_href}"
        # Screenshot after negative validation
        page.screenshot(path="screenshots/tc_example_neg_wrong_href_06/06_after_negative_assert.png")

    except Exception as e:
        print(f"ERROR in test_tc_example_neg_wrong_href_06: {e}")
        traceback.print_exc()
        # Take error screenshot before re-raising
        page.screenshot(path="screenshots/tc_example_neg_wrong_href_06/error.png")
        raise