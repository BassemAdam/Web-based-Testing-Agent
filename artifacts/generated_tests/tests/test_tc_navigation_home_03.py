import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

@pytest.mark.functional
@pytest.mark.happy_path
def test_TC_NAVIGATION_HOME_03(page):
    # Instantiate the home page object using the provided page fixture
    home_page = Page_0Page(page)
    
    # Navigate to the start URL if the test begins on page_0
    home_page.navigate()
    
    # Click the 'Home' button to navigate back to the main YouTube page
    home_page.navigate_to_home()
    
    # Add assertions or other verifications as needed
    expect(page).to_have_url("https://www.youtube.com/")