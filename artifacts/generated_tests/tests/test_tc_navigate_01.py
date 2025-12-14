import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

def test_TC_NAVIGATE_01(page):
    home_page = Page_0Page(page)
    home_page.navigate()
    
    # Click the 'Learn more' link to navigate to the domains section of IANA
    learn_more_link = home_page.get_element("a|Learn more|")
    learn_more_link.click()
    
    # Instantiate the Page 1 object after navigation
    domain_page = Page_1Page(page)
    
    # Ensure that the user is on the 'Example Domains' page and not on the home page
    expect(page).to_have_url("https://www.iana.org/domains")