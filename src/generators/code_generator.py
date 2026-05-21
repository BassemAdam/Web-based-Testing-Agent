import json
import os
import ast
import re
from typing import Dict, List, Any
from loguru import logger
from src.agent.llm.ollama_client import CopilotClient
from src.agent.metrics.metrics_recorder import get_metrics_tracker, PHASE_CODE_GENERATION
from .prompts import TEST_GENERATION_PROMPT, FIX_SYNTAX_PROMPT

class CodeGenerator:
    
    def __init__(self, test_plan_path: str, output_dir: str, feedback: str = None):
        """
        Initialize the generator.
        
        Args:
            test_plan_path: Path to the JSON file containing the test plan.
            output_dir: Directory where the generated code will be saved.
            feedback: Optional user feedback to guide code generation.
        """
        self.test_plan_path = test_plan_path
        self.output_dir = output_dir
        self.feedback = feedback or "No specific feedback provided."
        self._metrics = get_metrics_tracker()
        
        # Initialize the AI client
        # self.llm = CopilotClient(
        #     model="gpt-5-mini",  # or "claude-3.5-sonnet"
        #     config={
        #         "temperature": 0.2,
        #         "max_tokens": 4096,
        #         "num_ctx": 8192,
        #         "num_predict": 4096,
        #     },
        # )
        self.llm = CopilotClient(
    model="gpt-5-mini",  # or "claude-3.5-sonnet"
    config={
        # Sets the thinking depth: "minimal", "low", "medium", or "high"
        "reasoning_effort": "high", 
        
        # Max tokens must account for both the thinking tokens AND the final visible response
        "max_completion_tokens": 4096, 
        
        # Optional: Control how wordy the actual response is ("low", "medium", "high")
        "verbosity": "medium" 
    },
)
        # Load the test plan data
        self.test_plan = self._load_test_plan()
        self.pages = self.test_plan.get("pages", {})
        
        # Setup output directory
        self.tests_dir = os.path.join(output_dir, "tests")
        os.makedirs(self.tests_dir, exist_ok=True)

    def _load_test_plan(self) -> Dict:
        """Reads the test plan JSON file."""
        with open(self.test_plan_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _delete_existing_tests(self):
        """Delete all existing test files and their screenshots before generating new ones."""
        if os.path.exists(self.tests_dir):
            test_files = [f for f in os.listdir(self.tests_dir) if f.startswith('test_') and f.endswith('.py')]
            for test_file in test_files:
                file_path = os.path.join(self.tests_dir, test_file)
                os.remove(file_path)
                logger.info(f"🗑️  Deleted {test_file}")
            if test_files:
                logger.info(f"✅ Deleted {len(test_files)} existing test files")
        
        # Delete screenshot directories
        screenshots_dir = os.path.join(self.output_dir, "screenshots")
        if os.path.exists(screenshots_dir):
            import shutil
            screenshot_folders = [f for f in os.listdir(screenshots_dir) if os.path.isdir(os.path.join(screenshots_dir, f))]
            for folder in screenshot_folders:
                folder_path = os.path.join(screenshots_dir, folder)
                shutil.rmtree(folder_path)
                logger.info(f"🗑️  Deleted screenshots: {folder}/")
            if screenshot_folders:
                logger.info(f"✅ Deleted {len(screenshot_folders)} screenshot folders")
    
    def generate(self, feedback: str = None, test_filename: str = None):
        """
        Main execution method.
        Orchestrates the entire code generation process.
        
        Args:
            feedback: Optional feedback to guide code generation. 
                     If provided, overrides the feedback from __init__.
            test_filename: Optional specific test filename to regenerate.
                          If provided, only that test will be regenerated with feedback.
                          If None/empty, all tests will be regenerated with feedback.
        """
        # Start Phase 2: Code Generation tracking
        self._metrics.start_phase(PHASE_CODE_GENERATION)
        
        # Update feedback if provided
        if feedback is not None:
            self.feedback = feedback if feedback.strip() else "No specific feedback provided."
            logger.info(f"📝 Updated feedback: {self.feedback[:100]}...")
        
        logger.info("🚀 Starting code generation...")
        
        # Check if a specific test filename is provided
        if test_filename and test_filename.strip():
            # Regenerate only the specific test
            target_test = test_filename.strip()
            # Ensure it starts with "test_" and ends with ".py"
            if not target_test.startswith('test_'):
                target_test = 'test_' + target_test
            if not target_test.endswith('.py'):
                target_test = target_test.replace('.py', '') + '.py'
            
            # Remove .py for processing
            target_test_name = target_test.replace('.py', '')
            
            logger.info(f"🎯 Regenerating specific test: {target_test_name}")
            self.generate_specific_test(target_test_name)
        else:
            # Delete existing tests and regenerate all
            logger.info("📝 Applying feedback to all tests")
            self._delete_existing_tests()
            self.generate_test_files()
        
        self._generate_conftest()
        
        # End Phase 2 tracking
        self._metrics.end_phase()
        
        logger.info(f"✅ Code generation complete! Check folder: {self.output_dir}")

    def generate_test_files(self):
        """Generates standalone Test Files (one per test case)."""
        logger.info("🧪 Generating Test Files...")
        
        test_cases = self.test_plan.get("test_cases", [])
        
        for test_case in test_cases:
            self._generate_single_test_file(test_case)
    
    def generate_specific_test(self, test_name: str):
        """Regenerate a specific test file based on test name."""
        # Extract test ID from test name (e.g., "test_tc_navigate_course_01" -> "TC_NAV_COURSE_01" or similar)
        # Try to match with test cases in the plan
        test_cases = self.test_plan.get("test_cases", [])
        
        # Normalize test name for comparison
        normalized_target = test_name.lower().replace('test_', '')
        
        found = False
        for test_case in test_cases:
            test_id = test_case.get("id", "").lower()
            if test_id == normalized_target or f"test_{test_id}" == test_name.lower():
                logger.info(f"✅ Found matching test case: {test_case.get('id')}")
                # Delete the old test file if it exists
                old_file = os.path.join(self.tests_dir, f"test_{test_id}.py")
                if os.path.exists(old_file):
                    os.remove(old_file)
                    logger.info(f"🗑️  Deleted old version: test_{test_id}.py")
                
                # Delete screenshots for this test
                screenshots_dir = os.path.join(self.output_dir, "screenshots", test_id)
                if os.path.exists(screenshots_dir):
                    import shutil
                    shutil.rmtree(screenshots_dir)
                    logger.info(f"🗑️  Deleted screenshots: {test_id}/")
                
                # Generate the new version with feedback
                self._generate_single_test_file(test_case)
                found = True
                break
        
        if not found:
            logger.warning(f"⚠️  Could not find test case matching '{test_name}' in test plan")
            logger.warning(f"Available test IDs: {[tc.get('id') for tc in test_cases]}")

    def _load_page_html(self) -> str:
        """Load raw page HTML from the site snapshot referenced in the test plan."""
        snapshot_path = self.test_plan.get("snapshot_file", "")
        if not snapshot_path or not os.path.exists(snapshot_path):
            return ""
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
            for _page_id, page_data in snapshot.get("pages", {}).items():
                html = page_data.get("snapshot", {}).get("raw_html", "")
                if html:
                    return html
        except Exception:
            pass
        return ""

    def _enrich_selectors_with_custom_dropdown(
        self, selectors: List[Dict], page_html: str
    ) -> List[Dict]:
        """
        For each 'select' element selector, check whether the native <select> is
        hidden by CSS and backed by a .custom-dropdown div widget in the page HTML.
        If so, replace best_locator with the visible widget locator and add an
        interaction_note so the LLM generates the correct click-based interaction
        instead of Playwright's select_option() which fails on hidden selects.
        """
        import re

        if not page_html:
            return selectors

        enriched = []
        for selector in selectors:
            sel = selector.copy()
            element_key = sel.get("element_key", "")
            css_selector = sel.get("css_selector", "")

            # Only process select elements
            if not element_key.startswith("select||"):
                enriched.append(sel)
                continue

            # Extract element id from css_selector, e.g. "#state" → "state"
            id_match = re.match(r"^#([\w-]+)$", css_selector.strip())
            if not id_match:
                enriched.append(sel)
                continue

            elem_id = id_match.group(1)
            wrapper_id = f"div_id_{elem_id}"

            # Check if CSS hides this select via display:none on wrapper
            css_hidden = bool(
                re.search(
                    rf"#div_id_{re.escape(elem_id)}\s*\.form-select[^{{]*\{{[^}}]*display\s*:\s*none",
                    page_html,
                )
            )

            # Check if a .custom-dropdown div lives inside the same wrapper
            has_custom_dropdown = bool(
                re.search(
                    rf'id="{re.escape(wrapper_id)}"[^>]*>.*?class="custom-dropdown"',
                    page_html,
                    re.DOTALL,
                )
            )

            if css_hidden or has_custom_dropdown:
                # Check whether this select is initially disabled (e.g. city depends on state)
                is_disabled = bool(
                    re.search(
                        rf'<select[^>]*id="{re.escape(elem_id)}"[^>]*disabled',
                        page_html,
                    )
                )

                sel["best_locator"] = (
                    f"page.locator('#{wrapper_id} .custom-dropdown-control')"
                )
                sel["custom_dropdown"] = True
                sel["wrapper_id"] = wrapper_id
                sel["native_select_id"] = elem_id
                sel["is_disabled_initially"] = is_disabled
                disabled_note = (
                    f"\n  NOTE: This dropdown is initially disabled. Before clicking it, wait:\n"
                    f"  page.wait_for_function(\"!document.querySelector('#{elem_id}').disabled\", timeout=10000)"
                    if is_disabled
                    else ""
                )
                sel["interaction_note"] = (
                    f"IMPORTANT: #{elem_id} native <select> is hidden via CSS (display:none). "
                    f"Do NOT use select_option(). Instead interact with the custom dropdown widget:\n"
                    f"  container = page.locator('#{wrapper_id}')\n"
                    f"  container.scroll_into_view_if_needed()\n"
                    f"  container.locator('.custom-dropdown-control').click()  # opens the menu\n"
                    f"  page.wait_for_timeout(300)\n"
                    f"  container.locator('.custom-dropdown-option[data-value=\"VALUE\"]').click()\n"
                    f"  # Assert via the native select's JS-updated value:\n"
                    f"  assert page.locator('#{elem_id}').evaluate('el => el.value') == 'VALUE'"
                    f"{disabled_note}"
                )
                logger.info(
                    f"🔍 Detected hidden select #{elem_id} with custom dropdown widget "
                    f"(wrapper: #{wrapper_id}, initially_disabled: {is_disabled})"
                )

            enriched.append(sel)
        return enriched

    def _enrich_selectors_with_modal_dismiss(
        self, selectors: List[Dict], page_html: str
    ) -> List[Dict]:
        """
        Detect buttons that have data-bs-dismiss="modal" (Bootstrap modal close buttons).
        These buttons are inside a hidden modal container and are NOT directly visible on
        page load.  They can only be interacted with AFTER the modal is opened.

        For each such selector, adds an interaction_note that:
        - Identifies the enclosing modal id
        - Warns the LLM NOT to assert visibility before the modal is visible
        - Explains the correct pre-condition: wait for the modal to be visible first
        """
        import re

        if not page_html:
            return selectors

        enriched = []
        for selector in selectors:
            sel = selector.copy()
            css_selector = (sel.get("css_selector") or "").strip()

            # Only inspect elements that have a simple id selector (e.g. "#closeLargeModal")
            id_match = re.match(r"^#([\w-]+)$", css_selector)
            if not id_match:
                enriched.append(sel)
                continue

            elem_id = id_match.group(1)

            # Check if this element has data-bs-dismiss="modal" in the page HTML
            is_modal_dismiss = bool(
                re.search(
                    rf'id="{re.escape(elem_id)}"[^>]*data-bs-dismiss="modal"|'
                    rf'data-bs-dismiss="modal"[^>]*id="{re.escape(elem_id)}"',
                    page_html,
                )
            )
            if not is_modal_dismiss:
                enriched.append(sel)
                continue

            # Find the enclosing modal id by searching backwards from the element
            idx = page_html.find(f'id="{elem_id}"')
            html_before = page_html[:idx]
            modal_match = re.findall(
                r'<div[^>]*class="[^"]*\bmodal\b[^"]*"[^>]*id="([^"]+)"',
                html_before,
            )
            modal_id = modal_match[-1] if modal_match else "the-modal"

            sel["modal_dismiss"] = True
            sel["enclosing_modal_id"] = modal_id
            sel["interaction_note"] = (
                f"IMPORTANT: #{elem_id} has data-bs-dismiss='modal' — it is a close button "
                f"INSIDE a Bootstrap modal (#{modal_id}).  "
                f"It is NOT visible on page load. "
                f"You MUST wait for the modal to be visible before asserting or clicking this button:\n"
                f"  page.locator('#{modal_id}').wait_for(state='visible', timeout=10000)\n"
                f"  # Only then assert/click:\n"
                f"  expect(page.locator('#{elem_id}')).to_be_visible()\n"
                f"  page.locator('#{elem_id}').click()\n"
                f"  # After clicking, verify modal is dismissed:\n"
                f"  expect(page.locator('#{modal_id}')).not_to_be_visible(timeout=5000)"
            )
            logger.info(
                f"\U0001f50d Detected modal dismiss button #{elem_id} inside modal #{modal_id}"
            )

            enriched.append(sel)
        return enriched

    def _select_best_locator(
        self,
        css_selector: str | None,
        xpath: str | None,
        element_key: str,
        playwright_locator: str | None = None,
    ) -> str:
        """
        Select the best Playwright locator from available options.
        Priority: playwright_locator from design phase > Semantic > ID > CSS > XPath > fallback
        """
        # 0. Use the locator already computed by MultiPageTestDesignPipeline (most accurate)
        if playwright_locator:
            return playwright_locator

        # 1. Parse element_key to build semantic locators (format: "tag|text|id|...")
        parts = element_key.split("|")
        tag = parts[0].strip() if parts else ""
        text = parts[1].strip() if len(parts) > 1 else ""
        elem_id = parts[2].strip() if len(parts) > 2 else ""

        # 2. Prefer semantic locators (most reliable)
        if tag == "a" and text:
            safe_text = text.replace("'", "\\'")
            return f"page.get_by_role('link', name='{safe_text}')"
        if tag == "button" and text:
            safe_text = text.replace("'", "\\'")
            return f"page.get_by_role('button', name='{safe_text}')"

        # 3. Use ID if available (second most reliable)
        if elem_id:
            return f"page.locator('#{elem_id}')"

        # 4. Prefer specific CSS selectors
        if css_selector and css_selector not in ["a", "button", "input", "select"]:
            if "[" in css_selector or "#" in css_selector or "." in css_selector:
                return f'page.locator("{css_selector}")'
            if ":has-text(" in css_selector:
                return f'page.locator("{css_selector}")'

        # 5. Use XPath if it has text content
        if xpath and "contains(text()" in xpath:
            return f'page.locator("{xpath}")'

        # 6. Fallback to CSS selector or XPath
        if css_selector:
            return f'page.locator("{css_selector}")'
        if xpath:
            return f'page.locator("{xpath}")'

        return f'page.locator("{tag}")'

    def _generate_single_test_file(self, test_case: Dict):
        """
        Generates a standalone test file for a test case.
        Uses selectors directly from the test plan - no Page Objects.
        """
        test_id = test_case.get("id", "unknown_test")
        logger.info(f"🧪 Generating Test File for {test_id}...")
        
        start_url = self.test_plan.get("start_url", "")
        
        # Build selector information with best locators.
        # Per-selector: prefer the playwright_locator stored on matching steps.
        step_locators: dict[str, str] = {}
        for s in test_case.get("steps", []):
            pl = s.get("playwright_locator")
            key = s.get("target", "")
            if pl and key:
                step_locators[key] = pl

        selectors_with_locators = []
        for selector in test_case.get("selectors", []):
            selector_copy = selector.copy()
            elem_key = selector.get("element_key", "")
            selector_copy["best_locator"] = self._select_best_locator(
                selector.get("css_selector"),
                selector.get("xpath"),
                elem_key,
                playwright_locator=step_locators.get(elem_key),
            )
            selectors_with_locators.append(selector_copy)

        # Detect hidden select / custom dropdown widgets and enrich selectors
        # so the LLM generates click-based interaction instead of select_option()
        page_html = self._load_page_html()
        selectors_with_locators = self._enrich_selectors_with_custom_dropdown(
            selectors_with_locators, page_html
        )
        # Detect modal dismiss buttons (data-bs-dismiss="modal") so the LLM knows
        # the modal must be open before asserting or clicking them
        selectors_with_locators = self._enrich_selectors_with_modal_dismiss(
            selectors_with_locators, page_html
        )

        # Enrich steps with all materialized fields for the prompt.
        enriched_steps = [
            {
                "step_number": s.get("step_number"),
                "page_id": s.get("page_id"),
                "page_url": s.get("page_url"),
                "action": s.get("action"),
                "target": s.get("target"),
                "input_value": s.get("input_value"),
                "details": s.get("details"),
                "expected_result": s.get("expected_result"),
                "playwright_locator": s.get("playwright_locator"),
            }
            for s in test_case.get("steps", [])
        ]

        # Build prompt for AI
        prompt = self._build_test_prompt(
            test_case=test_case,
            selectors=selectors_with_locators,
            start_url=start_url,
            enriched_steps=enriched_steps,
        )
        
        # Generate code
        code = self.llm.chat([{"role": "user", "content": prompt}])
        code = self._clean_code_markdown(code)
        
        # Add imports
        imports = """import pytest
from playwright.sync_api import Page, expect
import traceback

"""
        final_code = imports + code
        
        # Validate and fix syntax issues
        final_code = self._validate_and_fix_code(final_code)
        
        filename = f"test_{test_id.lower()}.py"
        self._save_file(self.tests_dir, filename, final_code)
        
        logger.info(f"✅ Generated {filename}")
    
    def _build_test_prompt(
        self,
        test_case: Dict,
        selectors: List[Dict],
        start_url: str,
        enriched_steps: List[Dict] | None = None,
    ) -> str:
        """
        Build the prompt for generating a standalone test.
        Passes the enriched step data (playwright_locator, expected_result, etc.)
        produced by MultiPageTestDesignPipeline so the LLM can use them directly.
        """
        # Merge enriched steps back into the test_case copy sent to the LLM
        tc_for_prompt = dict(test_case)
        if enriched_steps:
            tc_for_prompt["steps"] = enriched_steps

        return TEST_GENERATION_PROMPT.format(
            start_url=start_url,
            test_case_info=json.dumps(tc_for_prompt, indent=2),
            selectors_info=json.dumps(selectors, indent=2),
            pages_info=json.dumps(self.pages, indent=2),
            feedback=self.feedback,
            test_id=test_case.get('id', 'unknown').lower()
        )

    def _generate_conftest(self):
        """
        Generates 'conftest.py' for pytest configuration.
        Sets up the browser viewport.
        """
        if os.path.exists(os.path.join(self.tests_dir, "conftest.py")):
            logger.info("⏭️  Skipping conftest.py (already exists)")
            return
            
        content = """import pytest
import os


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {
            "width": 1280,
            "height": 720,
        },
    }


@pytest.fixture(autouse=True)
def ensure_screenshot_dirs(request):
    \"\"\"Create screenshot sub-directory for each test before it runs.\"\"\"
    test_name = request.node.name
    screenshot_dir = os.path.join("screenshots", test_name)
    os.makedirs(screenshot_dir, exist_ok=True)
"""
        self._save_file(self.tests_dir, "conftest.py", content)

    def _validate_and_fix_code(self, code: str, max_retries: int = 6) -> str:
        """
        Self-Correction Mechanism.
        Checks if the generated code has syntax errors. If so, asks AI to fix it.
        """
        for attempt in range(max_retries + 1):
            try:
                ast.parse(code)
                logger.info(f"✅ Code validation passed")
                return code  # Code is valid!
            except SyntaxError as e:
                logger.warning(f"⚠️ Syntax error detected: {e}. Attempting fix ({attempt+1}/{max_retries})...")
                
                if attempt == max_retries:
                    logger.error("❌ Failed to fix syntax error after retries.")
                    return code  # Return broken code as last resort
                
                # Ask AI to fix the specific error
                prompt = FIX_SYNTAX_PROMPT.format(
                    error_message=str(e),
                    code=code
                )
                code = self.llm.chat([{"role": "user", "content": prompt}])
                code = self._clean_code_markdown(code)
        return code

    def _clean_code_markdown(self, code: str) -> str:
        """Removes Markdown code blocks (```python ... ```) from AI response."""
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1].split("```")[0]
        return code.strip()

    def _save_file(self, directory: str, filename: str, content: str):
        """Helper to save content to a file."""
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"💾 Saved {filename}")
