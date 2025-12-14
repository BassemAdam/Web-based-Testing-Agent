from playwright.sync_api import Page, expect
from .base_page import BasePage

class Page_1Page(BasePage):
    URL = "https://www.iana.org/help/example-domains"
    
    def __init__(self, page: Page):
        super().__init__(page)
        self._Domains_link = page.get_by_role('link', name='Domains').nth(0)
        self._Protocols_link = page.get_by_role('link', name='Protocols').nth(0)
        self._Numbers_link = page.get_by_role('link', name='Numbers').nth(0)
        self._About_link = page.get_by_role('link', name='About').nth(0)
        self._RFC2606_link = page.get_by_role('link', name='RFC 2606').nth(0)
    
    def navigate_to_domains(self):
        self._Domains_link.click()
        expect(self.page).to_have_url("https://www.iana.org/domains")
    
    def navigate_to_protocols(self):
        self._Protocols_link.click()
        expect(self.page).to_have_url("https://www.iana.org/protocols")
    
    def navigate_to_numbers(self):
        self._Numbers_link.click()
        expect(self.page).to_have_url("https://www.iana.org/numbers")
    
    def navigate_to_about(self):
        self._About_link.click()
        expect(self.page).to_have_url("https://www.iana.org/about")
    
    def verify_links_present(self):
        expect(self._Domains_link).to_be_visible()
        expect(self._Protocols_link).to_be_visible()
        expect(self._Numbers_link).to_be_visible()
        expect(self._About_link).to_be_visible()
        expect(self._RFC2606_link).to_be_visible()
        