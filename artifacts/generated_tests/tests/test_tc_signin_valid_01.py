import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

@pytest.mark.functional
@pytest.mark.happy_path
def test_TC_SIGNIN_VALID_01(page):
    # Start URL is https://www.youtube.com/
    home_page = Page_0Page(page)
    home_page.navigate()
    
    # Navigate to the sign-in page
    home_page.navigate_to_signin()
    
    # Sign in with valid credentials
    login_page = Page_1Page(page)
    login_page.enter_valid_credentials("dodooooo@gmail.com", "lolo@gmail.com")
    login_page.click_next()
    
    # Assertions can be added here if needed, but the main focus is on actions and interactions