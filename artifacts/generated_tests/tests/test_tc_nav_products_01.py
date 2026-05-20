import pytest
from playwright.sync_api import Page, expect
import traceback

def test_tc_nav_products_01(page):
    try:
        # Step 1: Navigate to the application's home URL
        start_url = "https://automationexercise.com/"
        page.goto(start_url)
        # Screenshot immediately after navigation
        page.screenshot(path="screenshots/tc_nav_products_01/01_initial_page.png")

        # Step 2: Confirm home page is loaded by asserting the presence of the 'APIs list for practice' button
        home_apis_button = page.get_by_role('button', name='APIs list for practice')
        from playwright.sync_api import expect
        expect(home_apis_button).to_be_visible()
        # Screenshot after verifying the home button
        page.screenshot(path="screenshots/tc_nav_products_01/02_after_assert_home_button.png")

        # Step 3: Short pause to allow home page elements to load
        page.wait_for_timeout(1000)  # 1 second pause
        page.screenshot(path="screenshots/tc_nav_products_01/03_after_wait.png")

        # Step 4: Click the Products link in the main navigation to go to the All Products page
        products_link = page.get_by_role('link', name='\ue8f8 Products')
        products_link.click()
        page.screenshot(path="screenshots/tc_nav_products_01/04_after_click_products.png")

        # Step 5: Wait for navigation to the products page to complete
        page.wait_for_url("**/products")
        page.screenshot(path="screenshots/tc_nav_products_01/05_after_navigation_to_products.png")

        # Step 6: Verify the search input exists on the All Products page and is empty by default
        search_input = page.locator("#search_product").nth(0)
        expect(search_input).to_be_visible()
        # Assert the input is empty by default
        expect(search_input).to_have_value("")
        page.screenshot(path="screenshots/tc_nav_products_01/06_products_search_input_verified.png")

    except Exception as e:
        print(f"ERROR in test_tc_nav_products_01: {e}")
        import traceback
        traceback.print_exc()
        # Attempt to capture a screenshot on error
        try:
            page.screenshot(path="screenshots/tc_nav_products_01/error.png")
        except Exception:
            # If screenshot on error fails, still raise the original exception
            pass
        raise