import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_example_link_href_match_02(page: "Page"):
    try:
        # Step: Navigate to start URL
        start_url = "https://example.com"
        page.goto(start_url)
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_example_link_href_match_02/01_initial_page.png")

        # Step 1: Confirm the page loaded to the expected URL
        # Use expect to assert the page URL (example.com typically includes a trailing slash)
        expect(page).to_have_url("https://example.com/")
        page.screenshot(path="screenshots/tc_example_link_href_match_02/02_after_assert_page_loaded.png")

        # Step 2: Allow DOM to settle (wait)
        page.wait_for_timeout(1000)  # brief pause to let any dynamic content settle
        page.screenshot(path="screenshots/tc_example_link_href_match_02/03_after_wait.png")

        # Step 3: Locate the "Learn more" link using the provided selector and assert visibility
        learn_more_link = page.get_by_role("link", name="Learn more")
        expect(learn_more_link).to_be_visible()
        page.screenshot(path="screenshots/tc_example_link_href_match_02/04_after_assert_link_visible.png")

        # Step 4: Verify the href attribute equals the expected external URL
        expected_href = "https://iana.org/domains/example"
        expect(learn_more_link).to_have_attribute("href", expected_href)
        page.screenshot(path="screenshots/tc_example_link_href_match_02/05_after_assert_href.png")

    except Exception as e:
        print(f"ERROR in test_tc_example_link_href_match_02: {e}")
        import traceback
        traceback.print_exc()
        # Capture screenshot on error before re-raising
        page.screenshot(path="screenshots/tc_example_link_href_match_02/error.png")
        raise