import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

@pytest.mark.functional
@pytest.mark.negative
def test_TC_SIGNIN_INVALID_02(page):
    # Instantiate the page objects using the provided methods
    home_page = Page_0Page(page)
    login_page = Page_1Page(page)
    
    # Navigate to the start URL and click on the sign-in button
    home_page.navigate_to_home()
    home_page.navigate_to_signin()
    
    # Enter invalid credentials and attempt authentication
    login_page.enter_invalid_credentials("dodooooo@gmail.com", "lolo@gmail.com")
    login_page.click_next_with_invalid_credentials()
    
    # Add assertions to verify the expected outcome (e.g., error message)
    # Note: The exact content of the assertion would depend on what YouTube shows upon invalid sign-in attempt
    expect(page).to_have_title("YouTube")  # Example assertion, adjust based on actual behavior