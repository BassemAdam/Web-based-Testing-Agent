
PAGE_OBJECT_PROMPT = """
You are an expert Test Automation Engineer using Playwright and Python.
Your task is to generate a Page Object Model (POM) class for a specific web page.

Page Name: {page_name}
Page ID: {page_id}
Page URL: {page_url}

The following elements are interacted with on this page. I have selected the best locator for you:
{elements_info}

The following actions are performed on this page in the test scenarios:
{actions_info}

Requirements:
1.  **Class Structure**: Create a Python class named `{class_name}` inheriting from `BasePage`.
2.  **URL Property**: If a page_url is provided, add a class variable `URL = "{page_url}"` at the top of the class.
3.  **Locators**: Define locators as private attributes (e.g., `self._username_input = "..."`) in `__init__`. Use the `best_locator` provided in the JSON.
4.  **Methods**: Create methods for each logical action (e.g., `login(username, password)`).
    *   **Separation of Concerns**: The test should NOT call Playwright methods directly. The Page Object methods should handle `fill`, `click`, etc.
    *   **Default Inputs**: If an input requires text (like "type" action) and no specific value is clear, provide a sensible default value in the method signature (e.g., `def search(self, query="default search"):`).
5.  **Type Hinting**: Use proper type hints.
6.  **Imports**: Import `BasePage` from `.base_page`.
7.  **Output**: Output ONLY the Python code for the class.
"""

TEST_FILE_PROMPT = """
You are an expert Test Automation Engineer using Playwright and Python.
Your task is to generate a Pytest test file based on the provided Test Cases and Page Objects.

Start URL: {start_url}
Test Cases:
{test_cases_info}

Page Objects Available:
{page_objects_map}

Requirements:
1.  **Fixtures**: Use `pytest` fixtures. Assume a `page` fixture is available.
2.  **Test Setup**: Each test should start by navigating to the start URL if test begins on page_0.
    *   Example: `home_page = HomePage(page)` then `home_page.navigate()` (this uses the URL property)
3.  **Page Object Usage**: Instantiate Page Objects using the `page` fixture.
    *   Example: `home_page = HomePage(page)`
4.  **Separation of Concerns**: Do NOT use `page.locator(...)` or `page.click(...)` inside the test function. ONLY use methods defined in the Page Objects.
    *   Correct: `login_page.login("user", "pass")`
    *   Incorrect: `page.fill("#user", "user")`
5.  **Assertions**: Use `expect` from `playwright.sync_api` for assertions, or call verification methods on the Page Object.
6.  **Structure**: Implement each test case as a function `test_<id>`.
7.  **Output**: Output ONLY the Python code.
"""

FIX_SYNTAX_PROMPT = """
The following Python code has a syntax error:
{error_message}

Code:
{code}

Please fix the syntax error and return the corrected code. Output ONLY the code.
"""
