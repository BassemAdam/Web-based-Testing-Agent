import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_subscribe_valid_05(page: "Page"):
    import traceback
    from playwright.sync_api import expect

    try:
        # Step 1: Navigate to Home page
        page.goto("https://automationexercise.com/")
        page.screenshot(path="screenshots/tc_subscribe_valid_05/01_initial_page.png")

        # Step 2: Assert page loaded by checking 'APIs list for practice' button is present
        apis_button = page.get_by_role('button', name='APIs list for practice')
        expect(apis_button).to_be_visible()
        page.screenshot(path="screenshots/tc_subscribe_valid_05/02_after_assert_apis_button.png")

        # Step 3: Wait for subscribe field and button to render (wait for the subscribe input to be attached)
        subscribe_input_locator = page.locator('#susbscribe_email')
        subscribe_input_locator.wait_for(timeout=5000)
        page.screenshot(path="screenshots/tc_subscribe_valid_05/03_after_wait_for_subscribe_field.png")

        # Step 4: Enter a valid email in the subscribe field
        valid_email = "test.user+05@example.com"
        subscribe_input_locator.fill(valid_email)
        page.screenshot(path="screenshots/tc_subscribe_valid_05/04_after_fill_subscribe_email.png")
        # Verify the input has the entered value
        expect(subscribe_input_locator).to_have_value(valid_email)

        # Step 5: Click the subscribe button on the Home page
        subscribe_button = page.locator('#subscribe')
        expect(subscribe_button).to_be_enabled()
        subscribe_button.click()
        page.screenshot(path="screenshots/tc_subscribe_valid_05/05_after_click_subscribe_button.png")

        # Step 6: Wait for any client-side handling after clicking subscribe
        page.wait_for_timeout(1500)
        page.screenshot(path="screenshots/tc_subscribe_valid_05/06_after_wait_post_subscribe.png")

        # Step 7: Verify presence of the CSRF hidden input field.
        # Use the provided locator for the hidden input. Because hidden elements may not be visible,
        # check DOM presence via evaluate_all (safe for hidden elements) and also assert count via expect.
        csrf_locator = page.locator("input[name=\"csrfmiddlewaretoken\"]")
        # Get count via evaluate_all to avoid visibility issues
        csrf_count = csrf_locator.evaluate_all("els => els.length")
        assert csrf_count > 0, "Expected at least one csrfmiddlewaretoken input in the DOM"
        # Also assert with expect that at least one exists (to_have_count will check DOM count, not visibility)
        expect(csrf_locator).to_have_count(1, timeout=2000)
        page.screenshot(path="screenshots/tc_subscribe_valid_05/07_after_assert_csrf_present.png")

    except Exception as e:
        print(f"ERROR in test_tc_subscribe_valid_05: {e}")
        traceback.print_exc()
        # Capture error screenshot for debugging
        try:
            page.screenshot(path="screenshots/tc_subscribe_valid_05/error.png")
        except Exception:
            # If screenshot fails, at least print traceback
            pass
        raise