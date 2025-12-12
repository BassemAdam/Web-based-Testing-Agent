import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

# Assuming 'page' fixture is provided and imported as needed

def test_TC_NAVIGATE_HOME_03(page):
    # Instantiate the correct page object using the provided 'page' fixture
    home_page = Page_0Page(page)
    
    # Navigate to the start URL if the test begins on page_0
    home_page.navigate()
    
    # Perform the action as defined in the test case
    home_page.click_home()
    
    # Add assertions or verification steps as needed
    expect(page).to_have_url("https://www.youtube.com/")