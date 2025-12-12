import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

# Assuming 'page' fixture and Page Objects are already imported and available

@pytest.mark.functional
@pytest.mark.happy_path
def test_TC_SIGNIN_VALID_01(page):
    # Instantiate the home page object using the provided page fixture
    home_page = Page_0Page(page)
    
    # Navigate to the start URL if the test begins on page_0
    home_page.navigate()
    
    # Click the 'Sign in' button to navigate to the sign-in page
    home_page.click_sign_in()
    
    # Instantiate the login page object using the provided page fixture
    login_page = Page_1Page(page)
    
    # Enter valid email and password on the sign-in form
    login_page.enter_valid_credentials("valid@example.com", "validpassword")
    
    # Click 'Next' to proceed with authentication
    login_page.click_next()
    
    # Add assertions or further interactions as needed
    expect(page).to_have_url("https://www.youtube.com/signin?continue=https%3A%2F%2Fwww.youtube.com%2F&hl=en&next=https%3A%2F%2Fwww.youtube.com%2F")