import json
import os
import ast
import re
from typing import Dict, List, Any
from loguru import logger
from src.agent.llm.ollama_client import CopilotClient
from src.generators.prompts import TEST_GENERATION_PROMPT, FIX_SYNTAX_PROMPT

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
        
        # Initialize the AI client
        self.llm = CopilotClient(
            model="gpt-5-mini",  # or "claude-3.5-sonnet"
            config={
                "temperature": 0.2,
                "max_tokens": 4096,
                "num_ctx": 8192,
                "num_predict": 4096,
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

    def _select_best_locator(
        self, 
        css_selector: str | None, 
        xpath: str | None, 
        element_key: str
    ) -> str:
        """
        Select the best Playwright locator from available options.
        Priority: Semantic (get_by_role) > ID > CSS with attributes > XPath > fallback
        """
        # 1. Parse element_key to build semantic locators (format: "tag|text|id|...")
        parts = element_key.split("|")
        tag = parts[0].strip() if parts else ""
        text = parts[1].strip() if len(parts) > 1 else ""
        elem_id = parts[2].strip() if len(parts) > 2 else ""
        
        # 2. Prefer semantic locators (most reliable)
        if tag == "a" and text:
            # Escape single quotes in text
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
        
        # Build selector information with best locators
        selectors_with_locators = []
        for selector in test_case.get("selectors", []):
            selector_copy = selector.copy()
            selector_copy["best_locator"] = self._select_best_locator(
                selector.get("css_selector"),
                selector.get("xpath"),
                selector.get("element_key", "")
            )
            selectors_with_locators.append(selector_copy)
        
        # Build prompt for AI
        prompt = self._build_test_prompt(
            test_case=test_case,
            selectors=selectors_with_locators,
            start_url=start_url
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
    
    def _build_test_prompt(self, test_case: Dict, selectors: List[Dict], start_url: str) -> str:
        """
        Build the prompt for generating a standalone test.
        """
        return TEST_GENERATION_PROMPT.format(
            start_url=start_url,
            test_case_info=json.dumps(test_case, indent=2),
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
        from pathlib import Path

        @pytest.fixture(scope="session")
        def browser_context_args(browser_context_args):
            return {
                **browser_context_args,
                "viewport": {
                    "width": 1280,
                    "height": 720,
                }
            }
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
