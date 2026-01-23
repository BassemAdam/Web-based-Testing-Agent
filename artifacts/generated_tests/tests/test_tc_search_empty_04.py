import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_search_empty_04(page):
    import traceback
    from playwright.sync_api import expect
    try:
        # Step 1: Navigate to the Home page
        page.goto("https://automationexercise.com/")
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_search_empty_04/01_initial_page.png")

        # Step 2: Confirm Home page loaded by asserting presence of the 'APIs list for practice' button
        home_apis_button = page.get_by_role('button', name='APIs list for practice')
        expect(home_apis_button).to_be_visible()
        # Screenshot after assert on home page
        page.screenshot(path="screenshots/tc_search_empty_04/02_after_assert_home_button.png")

        # Step 3: Click the 'Products' link in the navigation to open products page
        products_link = page.get_by_role('link', name='\ue8f8 Products')
        products_link.click()
        # Screenshot after clicking Products
        page.screenshot(path="screenshots/tc_search_empty_04/03_after_click_products.png")

        # Step 4: Verify navigation to products page (URL) and that the search input is present
        expect(page).to_have_url("https://automationexercise.com/products")
        # Screenshot after navigation complete
        page.screenshot(path="screenshots/tc_search_empty_04/04_after_navigate_products.png")

        # Step 5: Locate the search input and ensure it's visible on the Products page
        search_input = page.locator('#search_product').nth(0)
        expect(search_input).to_be_visible()
        # Screenshot after locating search input
        page.screenshot(path="screenshots/tc_search_empty_04/05_after_assert_search_visible.png")

        # Step 6: Allow the page to be ready (network idle) before interacting further
        page.wait_for_load_state('networkidle')
        # Screenshot after wait
        page.screenshot(path="screenshots/tc_search_empty_04/06_after_wait.png")

        # Step 7: Explicitly clear the search field to simulate empty query
        search_input.fill('')
        # Screenshot after clearing the search field
        page.screenshot(path="screenshots/tc_search_empty_04/07_after_clear_search.png")

        # Step 8: Click the submit button for the (empty) search
        submit_search_button = page.locator('#submit_search').nth(0)
        submit_search_button.click()
        # Screenshot after clicking submit
        page.screenshot(path="screenshots/tc_search_empty_04/08_after_click_submit.png")

        # Step 9: Verify that the search input remains empty after submission
        expect(search_input).to_have_value('')
        # Final screenshot after verification
        page.screenshot(path="screenshots/tc_search_empty_04/09_after_assert_empty.png")

    except Exception as e:
        print(f"ERROR in test_tc_search_empty_04: {e}")
        traceback.print_exc()
        # Take an error screenshot before re-raising
        page.screenshot(path="screenshots/tc_search_empty_04/error.png")
        raise