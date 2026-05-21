
"""Prompts for test code generation using AI."""

TEST_GENERATION_PROMPT = """
You are an expert Test Automation Engineer using Playwright and Python.
Your task is to generate a standalone Pytest test function for the following test case.

═══════════════════════════════════════════════════════
CRITICAL RULES — READ BEFORE WRITING ANY CODE
═══════════════════════════════════════════════════════

1. USE PROVIDED LOCATORS ONLY
   - Use the `best_locator` field from "Available Selectors".
   - Do NOT invent new locators.

2. SCREENSHOT DIRECTORY — CREATE BEFORE USE
   - ALL screenshots go to the folder "screenshots/{test_id}/".
   - At the very start of the test, create that folder:
       import os
       os.makedirs("screenshots/{test_id}", exist_ok=True)
   - Take a screenshot IMMEDIATELY after the first page.goto() call.
   - Take a screenshot at key states only (after navigation, after fill, after click-submit, after assertion).
   - Use sequential numbering: 01_initial_page.png, 02_after_fill_name.png, etc.

3. ERROR HANDLING — ALWAYS RE-RAISE
   - Wrap the ENTIRE test body in a single try/except Exception block.
   - In the except block: log the error AND always end with `raise`.
   - Example:
       except Exception as e:
           print(f"ERROR in test_{test_id}: {{e}}")
           traceback.print_exc()
           try:
               page.screenshot(path="screenshots/{test_id}/error.png")
           except Exception:
               pass
           raise          # <-- REQUIRED, never omit this

4. FORM SUBMIT BUTTON
   - The form submit button is ALWAYS an `<input type="submit">` or a `<button type="submit">`.
   - Use `page.locator('#submit-id-submit')` or `page.locator('input[type="submit"]')`.
   - NEVER click a small icon button (text "event", "close", "search", etc.) as a form submit.
   - The "event" button near the Date of Birth field is the gijgo calendar icon — NOT a submit button.

5. SUBJECTS AUTOCOMPLETE — THREE-STEP PATTERN
   When typing into #subjectsAutocomplete:
   a. Fill the field with a partial word (e.g., "Ma" for "Maths"):
         page.locator('#subjectsAutocomplete').fill("Ma")
   b. Wait for the suggestion dropdown to appear:
         page.wait_for_selector('.suggestion-item', state='visible', timeout=3000)
   c. Click the first visible suggestion:
         page.locator('.suggestion-item').first.click()
   Valid subject names (MUST use exact spelling):
   "Maths", "Physics", "Chemistry", "Biology", "Computer Science",
   "Commerce", "Accounting", "Economics", "Arts", "Social Studies",
   "History", "Civics", "Hindi", "English", "Sanskrit"

6. DATE OF BIRTH FIELD
   - Use page.fill('#dateOfBirthInput', '10 Sep 1990') — format is "dd mmm yyyy".
   - Do NOT clear the field (it triggers a page crash bug).
   - Do NOT click the "event" calendar icon button.

7. AFTER FORM SUBMISSION — OUTCOME MUST MATCH THE TEST CASE
     - ONLY when the test case clearly describes a successful valid submission should you
         verify the Bootstrap success modal with id="resultsModal":
                 page.wait_for_selector('#resultsModal', state='visible', timeout=5000)
                 expect(page.locator('#resultsModal')).to_be_visible()
                 page.locator('#closeLargeModal').click()
     - For negative, boundary, validation, or ambiguous-acceptance tests (special chars,
         invalid email, empty fields, unsupported input, etc.), DO NOT blindly wait for the
         success modal.
     - Instead follow the step's expected_result/details and assert a deterministic outcome,
         such as: same page still visible, field value retained, submission blocked, or no
         success modal required.
     - NEVER use the "event" icon button as evidence that a modal is open.

8. RADIO BUTTONS AND CHECKBOXES
   - Radio buttons (gender): click the <label> element, not the hidden input.
     Use: page.locator('label[for="gender_0"]').click()
   - Checkboxes (hobbies): same pattern:
     page.locator('label[for="hobbies_0"]').click()

9. STATE / CITY DROPDOWNS (custom dropdown — NOT native <select>)
   - The native <select> is hidden; interact with the custom widget:
       # Select a state
       page.locator('#div_id_state .custom-dropdown-control').click()
       page.locator('#div_id_state .custom-dropdown-option:has-text("NCR")').click()
       # Then select a city (only enabled after state is chosen)
       page.locator('#div_id_city .custom-dropdown-control').click()
       page.locator('#div_id_city .custom-dropdown-option:has-text("Delhi")').click()

10. NO DUPLICATE IMPORTS
    - Do NOT import `traceback` or `from playwright.sync_api import expect` inside
      the function body — those are already imported at the top of the file.

11. NO PAGE RELOAD BOILERPLATE
    - Do NOT add a second page.goto() call at the start if the page was just loaded.
    - Do NOT add redundant assertions that the page is loaded before any action.
    - Go directly to the first meaningful step.

12. DATA FIDELITY — USE STEP input_value EXACTLY
    - Each step in "Test Case Information" has an "input_value" field. When writing a
      .fill() or .type() call for that step, use that EXACT value — do NOT substitute or
      change it.
    - If "input_value" starts with "NeedToAsk:", generate a placeholder constant at the
      top of the function and use it in the fill call:
          FIELD_VALUE = "REPLACE_ME"  # NeedToAsk: <description>
          page.locator('#someField').fill(FIELD_VALUE)
      Also add a comment: # TODO: Set FIELD_VALUE before running this test

═══════════════════════════════════════════════════════
TEST INPUTS
═══════════════════════════════════════════════════════

Start URL: {start_url}

Test Case Information:
{test_case_info}

Available Selectors (use best_locator field):
{selectors_info}

Page Information:
{pages_info}

User Feedback (CRITICAL — follow this guidance):
{feedback}

═══════════════════════════════════════════════════════
GENERATE THE FUNCTION
═══════════════════════════════════════════════════════

Generate a function named `test_{test_id}(page: Page)` that:
1. Creates the screenshots directory immediately (os.makedirs).
2. Navigates to start_url and takes the first screenshot.
3. Executes each test step with meaningful comments.
4. Takes screenshots at key moments (not after every trivial action).
5. Asserts expected outcomes from the test steps; only verify the success modal when the
    test case clearly represents a successful valid submission.
6. Wraps everything in try/except with re-raise.

Output ONLY the Python test function code (no imports — they are added automatically).

Example skeleton:
```python
def test_{test_id}(page: Page):
    import os
    os.makedirs("screenshots/{test_id}", exist_ok=True)
    try:
        page.goto("{start_url}")
        page.screenshot(path="screenshots/{test_id}/01_initial_page.png")

        # Fill first name
        page.locator('#firstName').fill("Alice")

        # Fill last name
        page.locator('#lastName').fill("Johnson")

        # Select gender via label
        page.locator('label[for="gender_0"]').click()

        # Fill mobile
        page.locator('#userNumber').fill("1234567890")
        page.screenshot(path="screenshots/{test_id}/02_after_form_fill.png")

        # Submit
        page.locator('input[type="submit"]').click()

        # Verify success modal
        page.wait_for_selector('#resultsModal', state='visible', timeout=5000)
        expect(page.locator('#resultsModal')).to_be_visible()
        page.screenshot(path="screenshots/{test_id}/03_after_submit.png")

        # Close modal
        page.locator('#closeLargeModal').click()

    except Exception as e:
        print(f"ERROR in test_{test_id}: {{e}}")
        traceback.print_exc()
        try:
            page.screenshot(path="screenshots/{test_id}/error.png")
        except Exception:
            pass
        raise
```
"""

FIX_SYNTAX_PROMPT = """
The following Python code has a syntax error:
{error_message}

Code:
{code}

Please fix the syntax error and return the corrected code. Output ONLY the code, no explanations.
"""
