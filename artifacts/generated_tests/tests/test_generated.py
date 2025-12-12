import pytest
from playwright.sync_api import Page, expect
from pages.home_page import HomePage
from pages.page_1_page import Page_1Page

import pytest
from playwright.sync_api import expect

# Assuming HomePage and LoginPage are defined in separate files or modules
from pages.home_page import HomePage
from pages.login_page import LoginPage

@pytest.fixture(scope="function")
def page(playwright):
    browser = playwright["chromium"]
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()
    browser.close()

# Test Case: Sign in with valid credentials
@pytest.mark.parametrize("test_data", [{}])
def test_TC_SIGNIN_VALID_01(page):
    home_page = HomePage(page)
    login_page = LoginPage(page)
    
    # Navigate to the start URL if starting on page_0
    home_page.navigate()
    home_page.click_sign_in()
    login_page.type_credentials("valid@example.com", "validpassword")
    login_page.click_next()
    
    # Add assertions here to verify the expected outcome
    expect(page).to_have_url("https://www.youtube.com/signin")  # Example assertion

# Test Case: Attempt to sign in with invalid credentials
@pytest.mark.parametrize("test_data", [{}])
def test_TC_SIGNIN_INVALID_02(page):
    home_page = HomePage(page)
    login_page = LoginPage(page)
    
    # Navigate to the start URL if starting on page_0
    home_page.navigate()
    home_page.click_sign_in()
    login_page.type_credentials("invalid@example.com", "invalidpassword")
    login_page.click_next()
    
    # Add assertions here to verify the expected outcome
    expect(page).to_have_url("https://www.youtube.com/signin")  # Example assertion

# Test Case: Navigate to Home from main menu
@pytest.mark.parametrize("test_data", [{}])
def test_TC_NAVIGATE_HOME_03(page):
    home_page = HomePage(page)
    
    # Navigate to the start URL if starting on page_0
    home_page.navigate()
    home_page.click_home()
    
    # Add assertions here to verify the expected outcome
    expect(page).to_have_url("https://www.youtube.com/")  # Example assertion