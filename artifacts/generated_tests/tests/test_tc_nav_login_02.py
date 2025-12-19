import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_nav_login_02(page):
    import traceback
    try:
        # Step 1: Navigate to the Home page (start_url)
        page.goto("https://automationexercise.com/")
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_nav_login_02/01_initial_page.png")

        # Step 2: Confirm Home page loaded by verifying the 'APIs list for practice' button is visible
        apis_button = page.get_by_role('button', name='APIs list for practice')
        expect(apis_button).to_be_visible()

        # Step 3: Click the 'Signup / Login' navigation link to go to the login page
        signup_login_link = page.get_by_role('link', name='Signup / Login')
        signup_login_link.click()
        # Screenshot after click action
        page.screenshot(path="screenshots/tc_nav_login_02/02_after_click.png")

        # Step 4: Verify navigation to the login page (expected URL)
        expect(page).to_have_url("https://automationexercise.com/login")

        # Step 5: Wait for the login form's email input to be available
        page.wait_for_selector("input[name=\"email\"]")
        # Screenshot after wait action
        page.screenshot(path="screenshots/tc_nav_login_02/03_after_wait.png")

        # Step 6: Verify the login email input exists (login email is the first email input)
        login_email_input = page.locator("input[name=\"email\"]").nth(0)
        expect(login_email_input).to_be_visible()

        # Step 7: Verify the login password input exists
        login_password_input = page.locator("input[name=\"password\"]")
        expect(login_password_input).to_be_visible()

        # Step 8: Verify presence of the Login button
        login_button = page.get_by_role('button', name='Login')
        expect(login_button).to_be_visible()

        # Step 9: Verify presence of the Signup button (signup form area)
        signup_button = page.get_by_role('button', name='Signup')
        expect(signup_button).to_be_visible()

        # Final screenshot after all verifications
        page.screenshot(path="screenshots/tc_nav_login_02/04_after_verification.png")

    except Exception as e:
        print(f"ERROR in test_tc_nav_login_02: {e}")
        traceback.print_exc()
        # Take an error screenshot before re-raising
        try:
            page.screenshot(path="screenshots/tc_nav_login_02/error.png")
        except Exception:
            # If screenshot fails, still print traceback and re-raise original exception
            traceback.print_exc()
        raise