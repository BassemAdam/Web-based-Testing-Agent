import pytest
from playwright.sync_api import Page, expect
from pages.page_0_page import Page_0Page

def test_TC_NAVIGATE_CART_01(page):
    # Step 1: Navigate to the start URL
    home_page = Page_0Page(page)
    home_page.navigate()

    # Step 2: Click on the 'Cart' link
    home_page.click_cart()

    # Step 3: Verify that the user is redirected to the cart page
    expect(page).to_have_url("https://automationexercise.com/view_cart")