
"""Prompts for test code generation using AI."""

TEST_GENERATION_PROMPT = """
You are an expert Test Automation Engineer using Playwright and Python.
Your task is to generate a standalone Pytest test function for the following test case.

**IMPORTANT RULES:**
1. Use ONLY the locators provided in the "Available Selectors" section below
2. Do NOT create Page Object classes - write the test directly using page.locator()
3. Use the EXACT locator syntax provided (e.g., page.get_by_role(), page.locator())
4. Add appropriate assertions using expect() from playwright.sync_api
5. **SCREENSHOT REQUIREMENTS (CRITICAL):**
   - Take a screenshot IMMEDIATELY after navigating to start_url (before any other action)
   - Take a screenshot AFTER EVERY SINGLE ACTION (click, fill, select, etc.)
   - Use descriptive filenames: page.screenshot(path="screenshots/{test_id}/01_initial_page.png")
   - Number screenshots sequentially: 01_, 02_, 03_, etc.
6. **ERROR HANDLING (CRITICAL):**
   - Wrap the ENTIRE test in try-except block
   - In except block: print the full exception with traceback using `import traceback; traceback.print_exc()`
   - Take a screenshot in the except block before re-raising: page.screenshot(path="screenshots/{test_id}/error.png")
   - Always re-raise the exception after logging
7. Handle navigation between pages using page.goto() or clicks
8. Use descriptive variable names and comments
9. Output ONLY the test function code (no imports, they will be added automatically)

Start URL: {start_url}

Test Case Information:
{test_case_info}

Available Selectors (use best_locator field):
{selectors_info}

Page Information:
{pages_info}

User Feedback (CRITICAL - follow this guidance):
{feedback}

Generate a test function named `test_{test_id}` that:
1. Wraps the ENTIRE test body in try-except block
2. Navigates to the start_url
3. Takes FIRST screenshot immediately after navigation (01_initial_page.png)
4. Follows the test steps in order
5. Takes a screenshot AFTER EACH action (02_after_click.png, 03_after_fill.png, etc.)
6. Adds assertions to verify expected outcomes
7. Handles any navigation or page transitions
8. In except block: print full traceback, take error screenshot, re-raise

Example structure:
```python
def test_{test_id}(page: Page):
    import traceback
    try:
        # Step 1: Navigate
        page.goto("{start_url}")
        page.screenshot(path="screenshots/{test_id}/01_initial_page.png")
        
        # Step 2: First action
        element = page.get_by_role(...)
        element.click()
        page.screenshot(path="screenshots/{test_id}/02_after_first_click.png")
        
        # Step 3: Next action
        ...
        page.screenshot(path="screenshots/{test_id}/03_after_second_action.png")
        
    except Exception as e:
        print(f"ERROR in test_{test_id}: {{e}}")
        traceback.print_exc()
        page.screenshot(path="screenshots/{test_id}/error.png")
        raise
```

Output ONLY the Python test function code.
"""

FIX_SYNTAX_PROMPT = """
The following Python code has a syntax error:
{error_message}

Code:
{code}

Please fix the syntax error and return the corrected code. Output ONLY the code, no explanations.
"""
