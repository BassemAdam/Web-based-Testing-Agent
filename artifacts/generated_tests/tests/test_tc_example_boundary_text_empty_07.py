import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_example_boundary_text_empty_07(page: Page):
    import traceback
    try:
        # Step 1: Navigate to the start URL
        page.goto("https://example.com")
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_example_boundary_text_empty_07/01_initial_page.png")

        # Use the provided locator for the "Learn more" link
        learn_more_link = page.get_by_role('link', name='Learn more')

        # Step 2: Assert the link is visible (confirm page loaded)
        expect(learn_more_link).to_be_visible()
        # Screenshot after assertion
        page.screenshot(path="screenshots/tc_example_boundary_text_empty_07/02_after_assert_page_loaded.png")

        # Step 3: Additional assert - ensure the href is the expected target
        link_href = learn_more_link.get_attribute("href")
        assert link_href == "https://iana.org/domains/example", f"Unexpected href on Learn more link: {link_href}"
        # Screenshot after href assertion
        page.screenshot(path="screenshots/tc_example_boundary_text_empty_07/03_after_assert_href.png")

        # Step 4: Wait to ensure text nodes are rendered (explicit wait for visibility)
        learn_more_link.wait_for(state="visible", timeout=5000)
        # Screenshot after wait
        page.screenshot(path="screenshots/tc_example_boundary_text_empty_07/04_after_wait.png")

        # Step 5: Boundary check - ensure the visible label is not an empty string
        visible_label = learn_more_link.inner_text()
        assert visible_label is not None and visible_label.strip() != "", "The 'Learn more' link text is empty or whitespace"
        # Also assert exact expected text for clarity
        expect(learn_more_link).to_have_text("Learn more")
        # Screenshot after final assertion
        page.screenshot(path="screenshots/tc_example_boundary_text_empty_07/05_after_final_assert.png")

    except Exception as e:
        print(f"ERROR in test_tc_example_boundary_text_empty_07: {e}")
        traceback.print_exc()
        # Screenshot on error before re-raising
        page.screenshot(path="screenshots/tc_example_boundary_text_empty_07/error.png")
        raise