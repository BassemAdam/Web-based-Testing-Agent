import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_example_link_href_protocol_03(page):
    try:
        # Step 1: Navigate to the start URL and capture initial state
        start_url = "https://example.com"
        page.goto(start_url)
        page.screenshot(path="screenshots/tc_example_link_href_protocol_03/01_initial_page.png")

        # Locate the "Learn more" link using the provided selector
        learn_more_link = page.get_by_role('link', name='Learn more')

        # Step 1 Assert: Confirm the page is loaded by checking the link is visible
        expect(learn_more_link).to_be_visible()
        page.screenshot(path="screenshots/tc_example_link_href_protocol_03/02_after_first_assert.png")

        # Step 2: Navigate again to explicitly follow the test steps (idempotent)
        page.goto(start_url)
        page.screenshot(path="screenshots/tc_example_link_href_protocol_03/03_after_second_navigate.png")

        # Step 3 Assert: Confirm the link is still present after navigation
        expect(learn_more_link).to_be_visible()
        page.screenshot(path="screenshots/tc_example_link_href_protocol_03/04_after_second_assert.png")

        # Step 4: Wait briefly to allow any rendering (small delay)
        page.wait_for_timeout(1000)  # 1000ms = 1s
        page.screenshot(path="screenshots/tc_example_link_href_protocol_03/05_after_wait.png")

        # Step 5 Assert: Protocol validation - ensure href uses secure scheme (https)
        # The expected exact href per selector is known; assert the attribute equals that value.
        expected_href = "https://iana.org/domains/example"
        expect(learn_more_link).to_have_attribute("href", expected_href)
        page.screenshot(path="screenshots/tc_example_link_href_protocol_03/06_after_protocol_assert.png")

    except Exception as e:
        print(f"ERROR in test_tc_example_link_href_protocol_03: {e}")
        import traceback
        traceback.print_exc()
        # Capture error state before re-raising
        page.screenshot(path="screenshots/tc_example_link_href_protocol_03/error.png")
        raise