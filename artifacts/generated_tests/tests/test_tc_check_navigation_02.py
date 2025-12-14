import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

def test_TC_CHECK_NAVIGATION_02(page):
    home_page = Page_0Page(page)
    #home_page.navigate_to_domains()
    
    domains_page = Page_1Page(page)
    domains_page.verify_links_present()
    
    # Asserting the URL check as per user feedback
    expect(page).to_have_url("https://www.iana.org/help/example-domains")