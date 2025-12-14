import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page
from pages.page_1_page import Page_1Page

def test_TC_CHECK_LINKS_03(page):
    home_page = Page_1Page(page)
    home_page.navigate()  # Assuming navigate is the method to go to the start URL
    
    #home_page.navigate_to_domains()
    current_url = page.url
    expect(page).to_have_url("https://www.iana.org/help/example-domains")
    
    home_page.navigate_to_protocols()
    current_url = page.url
    expect(page).to_have_url("https://www.iana.org/protocols")
    
    home_page.navigate_to_numbers()
    current_url = page.url
    expect(page).to_have_url("https://www.iana.org/numbers")
    
    home_page.navigate_to_about()
    current_url = page.url
    expect(page).to_have_url("https://www.iana.org/about")
    
    # home_page.navigate_to_rfc_2606()
    # current_url = page.url
    # expect(page).to_have_url("https://www.iana.org/rfc2606")