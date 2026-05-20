import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_search_perform_03(page):
    import traceback
    from playwright.sync_api import expect

    try:
        # Step 1: Navigate to the home page
        start_url = "https://automationexercise.com/"
        page.goto(start_url)
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_search_perform_03/01_initial_page.png")

        # Step 1 (assert): Confirm home page loaded by checking for the APIs list for practice button
        apis_button = page.get_by_role('button', name='APIs list for practice')
        expect(apis_button).to_be_visible()

        # Step 2 (click): Click the Products link to go to All Products page
        products_link = page.get_by_role('link', name='\ue8f8 Products')
        products_link.click()
        # Wait for navigation to complete and products page to load
        page.wait_for_load_state('networkidle')
        page.screenshot(path="screenshots/tc_search_perform_03/02_after_click_products.png")

        # Step 3 (assert/wait): Ensure the search input is present on the products page
        search_input = page.locator('#search_product')
        # Wait for the search input to be available in the DOM and visible
        page.wait_for_selector('#search_product')
        expect(search_input).to_be_visible()
        page.screenshot(path="screenshots/tc_search_perform_03/03_after_wait_for_search_input.png")

        # Step 4 (type): Enter a valid search term into the search field
        search_term = "Dress"
        search_input.fill(search_term)
        page.screenshot(path="screenshots/tc_search_perform_03/04_after_fill_search_input.png")

        # Step 5 (click): Click the search submit button
        submit_button = page.locator('#submit_search')
        submit_button.click()
        # Wait for potential results/update to complete
        page.wait_for_load_state('networkidle')
        page.screenshot(path="screenshots/tc_search_perform_03/05_after_click_submit.png")

        # Step 6 (wait): Allow page to update (give extra time for client-side updates)
        page.wait_for_timeout(1000)
        page.screenshot(path="screenshots/tc_search_perform_03/06_after_wait_for_results.png")

        # Step 7 (assert): Verify the search input retains the typed value after submission
        expect(search_input).to_have_value(search_term)
        page.screenshot(path="screenshots/tc_search_perform_03/07_final_search_input_assert.png")

    except Exception as e:
        print(f"ERROR in test_tc_search_perform_03: {e}")
        traceback.print_exc()
        # Capture screenshot on error for debugging
        try:
            page.screenshot(path="screenshots/tc_search_perform_03/error.png")
        except Exception:
            # If screenshot fails, still re-raise original exception
            pass
        raise