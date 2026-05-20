import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_login_invalid_email_06(page: Page):
    import traceback
    import os
    try:
        # Ensure screenshot directory exists
        os.makedirs("screenshots/tc_login_invalid_email_06", exist_ok=True)

        # Step 1: Navigate to the start URL
        start_url = "https://automationexercise.com/"
        page.goto(start_url)
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_login_invalid_email_06/01_initial_page.png")

        # Step 1 (assert): Confirm main page loaded by checking presence of 'APIs list for practice' button
        apis_button = page.get_by_role('button', name='APIs list for practice')
        expect(apis_button).to_be_visible()
        # Screenshot after assert
        page.screenshot(path="screenshots/tc_login_invalid_email_06/02_after_assert_page_loaded.png")

        # Step 2: Navigate to Home page again to follow test steps (explicit navigation as per test case)
        page.goto(start_url)
        page.screenshot(path="screenshots/tc_login_invalid_email_06/03_after_navigate_home.png")

        # Step 3 (assert): Re-confirm page loaded
        apis_button_again = page.get_by_role('button', name='APIs list for practice')
        expect(apis_button_again).to_be_visible()
        page.screenshot(path="screenshots/tc_login_invalid_email_06/04_after_assert_page_loaded_again.png")

        # Step 4: Click the 'Signup / Login' link to go to login page
        signup_login_link = page.get_by_role('link', name='Signup / Login')
        signup_login_link.click()
        page.screenshot(path="screenshots/tc_login_invalid_email_06/05_after_click_signup_login.png")

        # Step 5 (assert): Confirm login page loaded by checking email input presence
        email_input = page.locator("input[name=\"email\"]").nth(0)
        expect(email_input).to_be_visible()
        page.screenshot(path="screenshots/tc_login_invalid_email_06/06_after_assert_login_page_loaded.png")

        # Step 6 (wait): Short wait to ensure inputs are interactable
        page.wait_for_timeout(1000)
        page.screenshot(path="screenshots/tc_login_invalid_email_06/07_after_wait_before_typing.png")

        # Step 7 (type): Enter an invalid email format into the login email field
        invalid_email = "invalid-email-format"  # intentionally invalid (no @ and domain)
        email_input.fill(invalid_email)
        page.screenshot(path="screenshots/tc_login_invalid_email_06/08_after_fill_email.png")

        # Step 8 (type): Enter a valid-looking password into the password field
        password_input = page.locator("input[name=\"password\"]")
        test_password = "ValidPass123!"
        password_input.fill(test_password)
        page.screenshot(path="screenshots/tc_login_invalid_email_06/09_after_fill_password.png")

        # Step 9 (click): Click the Login button to attempt sign-in
        login_button = page.get_by_role('button', name='Login')
        login_button.click()
        page.screenshot(path="screenshots/tc_login_invalid_email_06/10_after_click_login.png")

        # Step 10 (wait): Short wait to allow any client-side validation to occur
        page.wait_for_timeout(1000)
        page.screenshot(path="screenshots/tc_login_invalid_email_06/11_after_wait_post_submit.png")

        # Step 11 (assert): Verify the email input retained the invalid value after attempting login
        # Re-fetch locator to ensure up-to-date state
        email_input_after = page.locator("input[name=\"email\"]").nth(0)
        expect(email_input_after).to_have_value(invalid_email)
        page.screenshot(path="screenshots/tc_login_invalid_email_06/12_after_assert_email_retained.png")

        # Step 12 (assert): Verify the Login button remains present on the page (no navigation away)
        login_button_after = page.get_by_role('button', name='Login')
        expect(login_button_after).to_be_visible()
        page.screenshot(path="screenshots/tc_login_invalid_email_06/13_after_assert_login_button_present.png")

    except Exception as e:
        print(f"ERROR in test_tc_login_invalid_email_06: {e}")
        traceback.print_exc()
        # Attempt to capture a screenshot of the error state
        try:
            page.screenshot(path="screenshots/tc_login_invalid_email_06/error.png")
        except Exception:
            # If screenshot fails, still re-raise after logging traceback
            pass
        raise