import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_signup_name_special_chars_07(page):
    import traceback
    try:
        # Start URL
        start_url = "https://automationexercise.com/"

        # Step 1: Navigate to start URL
        page.goto(start_url)
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/01_initial_page.png")

        # Step 2: Confirm home page loaded by asserting the presence of the 'APIs list for practice' button
        apis_button = page.get_by_role('button', name='APIs list for practice')
        from playwright.sync_api import expect
        expect(apis_button).to_be_visible()
        # Screenshot after assert
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/02_after_assert_home_loaded.png")

        # Step 3: Click the 'Signup / Login' link to access the signup form
        signup_login_link = page.get_by_role('link', name='Signup / Login')
        signup_login_link.click()
        # Screenshot after click
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/03_after_click_signup_link.png")

        # Step 4: Confirm login/signup page loaded by asserting presence of email input(s)
        # There are typically two email inputs on this page (login and signup). Assert visibility of at least the first two.
        email_input_first = page.locator("input[name=\"email\"]").nth(0)
        expect(email_input_first).to_be_visible()
        # Also check the second email input that corresponds to signup (if present)
        email_input_second = page.locator("input[name=\"email\"]").nth(1)
        expect(email_input_second).to_be_visible()
        # Screenshot after asserting email inputs
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/04_after_assert_login_page.png")

        # Step 5: Short wait to ensure form elements are interactive
        page.wait_for_timeout(500)  # 0.5s wait
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/05_after_wait.png")

        # Step 6: Confirm the name field is present before typing special characters
        name_input = page.locator("input[name=\"name\"]")
        expect(name_input).to_be_visible()
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/06_after_assert_name_present.png")

        # Step 7: Enter special characters and script-like payload into the signup name field
        special_payload = "<script>alert('xss')</script> !@#$%^&*()_+-=[]{};:'\",.<>/?`~"
        # Use fill to set the input value reliably
        name_input.fill(special_payload)
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/07_after_fill_name.png")

        # Step 8: Click the 'Signup' button to attempt submission
        signup_button = page.get_by_role('button', name='Signup')
        signup_button.click()
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/08_after_click_signup_button.png")

        # Step 9: Short wait to allow submission handling
        page.wait_for_timeout(1000)  # 1s wait
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/09_after_wait_post_submit.png")

        # Step 10: Verify the name field contains the exact string typed (local assertion)
        # Re-locate the name input in case DOM updated
        name_input_after = page.locator("input[name=\"name\"]")
        expect(name_input_after).to_have_value(special_payload)
        page.screenshot(path="screenshots/tc_signup_name_special_chars_07/10_after_assert_name_value.png")

    except Exception as e:
        print(f"ERROR in test_tc_signup_name_special_chars_07: {e}")
        traceback.print_exc()
        # Attempt to capture a screenshot of the error state
        try:
            page.screenshot(path="screenshots/tc_signup_name_special_chars_07/error.png")
        except Exception:
            # If screenshot fails, still re-raise after logging traceback
            pass
        raise