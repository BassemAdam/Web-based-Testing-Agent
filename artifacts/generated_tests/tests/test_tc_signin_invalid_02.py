import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

def test_TC_SIGNIN_INVALID_02(page):
    home_page = Page_0Page(page)
    home_page.navigate()
    
    # Click the 'Sign in' button to navigate to the sign-in page
    home_page.click_sign_in()
    
    # Instantiate the second page object for the sign-in form
    login_page = Page_1Page(page)
    
    # Enter invalid email and password on the sign-in form
    login_page.enter_invalid_credentials()
    
    # Click 'Next' to attempt authentication
    login_page.click_next()
    
    # Add assertions or verification steps here if necessary
    expect(page).to_have_url("https://accounts.google.com/signin/v2/identifier?continue=https%3A%2F%2Fwww.youtube.com&passive=true&hl=en&flowName=GlifWebSignIn")