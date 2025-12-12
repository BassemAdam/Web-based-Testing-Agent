
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

FIX_SYNTAX_PROMPT = """
The following Python code has a syntax error:
{error_message}

Code:
{code}

Please fix the syntax error and return the corrected code. Output ONLY the code.
"""

SINGLE_TEST_FILE_PROMPT = """
You are an expert Test Automation Engineer using Playwright and Python.
Your task is to generate a Pytest test file for a SINGLE test case based on the provided Test Case and Page Objects.

Start URL: {start_url}
Test Case:
{test_case_info}

Page Objects Available (with their methods):
{page_objects_info}

User Feedback (CRITICAL - You MUST follow this):
{feedback}

Requirements:
0.  **Do Not Invent Page Objects**: You MUST ONLY use the exact Page Object class names provided in `Page Objects Available`.
    - Do NOT guess names like `LoginPage` / `HomePage`.
    - When a step references `page_id`, you MUST use the class mapped for that `page_id`.
1.  **No Imports / No Fixtures**: Do NOT include any `import ...` / `from ... import ...` lines and do NOT define fixtures.
    - Assume the file will be wrapped with the required imports and a `page` fixture already exists.
2.  **Test Setup**: The test should start by navigating to the start URL if the test begins on page_0.
    *   Example: `home_page = Page_0Page(page)` then `home_page.navigate()` (this uses the URL property)
3.  **Page Object Usage**: Instantiate Page Objects using the `page` fixture.
    *   Example: `home_page = Page_0Page(page)`
4.  **Use ONLY Existing Methods**: ONLY call methods that are explicitly listed in the "Page Objects Available" section.
    *   Do NOT invent method names like `type_credentials()` or `click_next()` if they are not listed.
    *   If a method doesn't exist, use the closest matching method with appropriate parameters.
5.  **Separation of Concerns**: Do NOT use `page.locator(...)` or `page.click(...)` inside the test function.
    *   Correct: `login_page.login("user", "pass")`
    *   Incorrect: `page.fill("#user", "user")`
6.  **Assertions**: Use `expect` from `playwright.sync_api` for assertions, or call verification methods on the Page Object.
7.  **Structure**: Implement the test case as a single function `test_<test_case_id>` (use the ID from the test case).
8.  **Output**: Output ONLY the Python code.
"""

VALIDATE_PAGE_OBJECT_PROMPT = """
You are a code reviewer for Playwright Page Objects.

Page Object Code:
{page_object_code}

Expected Selectors from Test Plan:
{expected_selectors}

Your task:
1. Check if the Page Object has placeholder locators like `"best_locator"` or `"another_best_locator"`
2. Replace ALL placeholder locators with the actual selectors from the "Expected Selectors" section
3. Use the `_select_best_locator()` logic:
   - Prefer `page.get_by_role()` for buttons/links with text
   - Use the actual CSS selector or XPath provided
4. Ensure all methods use the correct locators
5. Output ONLY the corrected Python code
"""

VALIDATE_TEST_FILE_PROMPT = """
You are a code reviewer for Playwright tests.

Test File Code:
{test_code}

Available Page Object Methods:
{page_objects_methods}

Your task:
1. Check if the test calls methods that don't exist in the Page Objects
2. Replace invalid method calls with the correct methods from "Available Page Object Methods"
3. Ensure parameters match the method signatures
4. Do NOT add imports or fixtures
5. Output ONLY the corrected Python code (without imports)
"""

FIX_PAGE_OBJECT_USAGE_PROMPT = """
The following Playwright test file uses Page Object classes that are not defined in the project.
Your task is to replace these invalid class names with the correct ones from the provided list.

Available Page Objects (Map of Page ID -> Class Name):
{page_objects_map}

Invalid Test File Code:
{code}

Instructions:
1.  **Identify Invalid Classes**: Look for Page Object classes instantiated in the test (e.g., `HomePage(page)`, `LoginPage(page)`) that are NOT in the "Available Page Objects" values.
2.  **Map to Correct Class**:
    - `HomePage` usually corresponds to the class for `page_0`.
    - Use the context of the test (e.g., which page_id is being interacted with) to pick the right class.
3.  **Fix Imports**: Update the `from pages... import ...` lines to import the correct class from the correct module.
    - The module name is the snake_case version of the class name (e.g., `Page_0Page` -> `pages.page_0_page`).
4.  **Output**: Return ONLY the fully corrected Python code.
"""
