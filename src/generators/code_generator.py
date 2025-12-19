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

    def generate(self):
        """
        Main execution method.
        Orchestrates the entire code generation process.
        """
        logger.info("🚀 Starting code generation...")
        
        self.generate_test_files()
        self._generate_conftest()
        
        logger.info(f"✅ Code generation complete! Check folder: {self.output_dir}")

    def generate_test_files(self):
        """Generates standalone Test Files (one per test case)."""
        logger.info("🧪 Generating Test Files...")
        
        test_cases = self.test_plan.get("test_cases", [])
        
        for test_case in test_cases:
            self._generate_single_test_file(test_case)

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
