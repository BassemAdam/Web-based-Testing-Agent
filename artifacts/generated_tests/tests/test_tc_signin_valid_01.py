import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

def test_TC_SIGNIN_VALID_01(page):
    home_page = Page_0Page(page)
    home_page.navigate()
    home_page.click_sign_in()
    
    login_page = Page_1Page(page)
    login_page.type_email("valid@example.com")
    login_page.type_password("validPassword")
    login_page.click_next_for_valid_credentials()
    
    # Assuming the next page after successful sign-in has some specific element to assert success, e.g., a welcome message or dashboard loaded indicator
    expect(page).to_have_title("Dashboard | Your Site")  # Example assertion