import json
import os
import ast
import re
from typing import Dict, List, Any
from loguru import logger
from src.agent.llm.ollama_client import LLMClient
from src.generators.prompts import PAGE_OBJECT_PROMPT, TEST_FILE_PROMPT, FIX_SYNTAX_PROMPT

class CodeGenerator:
    """
    Generates Playwright test code (Page Objects and Test Files) from a Test Plan.
    """
    
    def __init__(self, test_plan_path: str, output_dir: str):
        """
        Initialize the generator.
        
        Args:
            test_plan_path: Path to the JSON file containing the test plan.
            output_dir: Directory where the generated code will be saved.
        """
        self.test_plan_path = test_plan_path
        self.output_dir = output_dir
        
        # Initialize the AI client (using DeepSeek Coder for code generation)
        self.llm = LLMClient(model="deepseek-coder-v2:16b")
        
        # Load the test plan data
        self.test_plan = self._load_test_plan()
        
        # Setup output directories
        self.pages_dir = os.path.join(output_dir, "pages")
        self.tests_dir = os.path.join(output_dir, "tests")
        
        # Create directories if they don't exist
        os.makedirs(self.pages_dir, exist_ok=True)
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
        
        # Step 1: Create the base class for all Page Objects
        self._generate_base_page()
        
        # Step 2: Organize test plan data by Page ID
        pages_data = self._group_data_by_page()
        
        # Step 3: Generate a Page Object file for each page found
        page_class_map = {}
        for page_id, data in pages_data.items():
            class_name = self._generate_page_object(page_id, data)
            page_class_map[page_id] = class_name
            
        # Step 4: Generate the actual test file using the Page Objects
        self._generate_test_file(page_class_map)
        
        # Step 5: Create the pytest configuration file
        self._generate_conftest()
        
        logger.info(f"✅ Code generation complete! Check folder: {self.output_dir}")

    def _generate_base_page(self):
        """
        Creates 'base_page.py'.
        This class holds common methods used by all pages (like navigation).
        """
        content = """from playwright.sync_api import Page
        class BasePage:
            \"\"\"Base class for all Page Objects.\"\"\"
            
            # Override this in subclasses if the page has a specific URL
            URL = None
            
            def __init__(self, page: Page):
                self.page = page

            def navigate(self, url: str = None):
                \"\"\"Navigate to a URL. Uses self.URL if no url is provided.\"\"\"
                target_url = url or self.URL
                if target_url:
                    self.page.goto(target_url)
                
            def get_title(self) -> str:
                return self.page.title()
        """
        self._save_file(self.pages_dir, "base_page.py", content)

    def _group_data_by_page(self) -> Dict[str, Dict]:
        """
        Organizes the flat list of test steps into groups based on which page they happen on.
        
        Returns:
            A dictionary where keys are page_ids (e.g., 'page_0') and values contain
            lists of elements and actions for that page.
        """
        pages = {}
        
        # 1. Collect all elements (selectors) used on each page
        for tc in self.test_plan.get("test_cases", []):
            for selector in tc.get("selectors", []):
                page_id = selector["page_id"]
                
                # Initialize page entry if new
                if page_id not in pages:
                    pages[page_id] = {"elements": [], "actions": set()}
                
                # Add element if not already present
                if selector not in pages[page_id]["elements"]:
                    pages[page_id]["elements"].append(selector)
            
            # 2. Collect all actions (clicks, types) performed on each page
            for step in tc.get("steps", []):
                page_id = step["page_id"]
                if page_id not in pages:
                    pages[page_id] = {"elements": [], "actions": set()}
                
                # Create a readable description of the action
                action_desc = f"{step['action']} on {step['target']} ({step.get('details', '')})"
                pages[page_id]["actions"].add(action_desc)
                
        return pages

    def _select_best_locator(self, selector_info: Dict) -> str:
        """
        Decides the best way to find an element (Locator Strategy).
        
        Strategy Priority:
        1. ID (Most reliable)
        2. Data-TestID (Best practice for testing)
        3. Semantic Role/Text (User-centric, e.g., "Button named Submit")
        4. CSS Selector (Standard)
        5. XPath (Least reliable, breaks easily)
        """
        css = selector_info.get("css_selector", "")
        xpath = selector_info.get("xpath", "")
        element_key = selector_info.get("element_key", "")
        
        # 1. ID is King (e.g., #submit-button)
        if css and "#" in css and " " not in css: 
            return f"page.locator('{css}')"
        
        # 2. Test IDs (e.g., [data-testid="submit"])
        if css and "[data-testid=" in css:
            return f"page.locator('{css}')"
            
        # 3. Semantic / Text Content (e.g., Button "Sign In")
        # element_key format is usually "tag|text|..."
        if element_key:
            parts = element_key.split('|')
            if len(parts) >= 2:
                tag = parts[0].lower()
                text = parts[1].strip()
                
                # Only use text if it's short and readable
                if text and len(text) < 50:
                    # Use 'get_by_role' for interactive elements
                    if tag in ['button', 'a', 'link']:
                        role = 'link' if tag == 'a' else tag
                        return f"page.get_by_role('{role}', name='{text}')"
                    
                    # Use 'get_by_text' for others
                    return f"page.get_by_text('{text}', exact=True)"

        # 4. CSS (Standard fallback)
        if css:
            return f"page.locator('{css}')"
            
        # 5. XPath (Last resort)
        if xpath:
            return f"page.locator('xpath={xpath}')"
            
        return "page.locator('UNKNOWN')"

    def _generate_page_object(self, page_id: str, data: Dict) -> str:
        """
        Generates the Python code for a single Page Object.
        """
        logger.info(f"📄 Generating Page Object for {page_id}...")
        
        # Prepare data for the AI prompt
        # We pre-calculate the best locator for each element so the AI doesn't have to guess
        elements_with_locators = []
        for el in data["elements"]:
            el_copy = el.copy()
            el_copy["best_locator"] = self._select_best_locator(el)
            elements_with_locators.append(el_copy)

        elements_json = json.dumps(elements_with_locators, indent=2)
        actions_list = "\n".join(data["actions"])
        
        # Determine a class name
        class_name = f"{page_id.capitalize()}Page"
        if page_id == "page_0":
            class_name = "HomePage" # Common convention
        
        # Get URL if this is the home page (page_0)
        page_url = self.test_plan.get("start_url") if page_id == "page_0" else None
        
        # Fill the prompt template
        prompt = PAGE_OBJECT_PROMPT.format(
            page_name=f"Page associated with ID {page_id}",
            page_id=page_id,
            page_url=page_url or "Not specified",
            elements_info=elements_json,
            actions_info=actions_list,
            class_name=class_name
        )
        
        # Ask AI to generate the code
        code = self.llm.chat([{"role": "user", "content": prompt}])
        
        # Clean and validate the code
        code = self._clean_code_markdown(code)
        code = self._validate_and_fix_code(code)
        
        # Save to file (convert ClassName to snake_case_filename.py)
        filename = self._to_snake_case(class_name) + ".py"
        self._save_file(self.pages_dir, filename, code)
            
        return class_name

    def _generate_test_file(self, page_class_map: Dict[str, str]):
        """
        Generates the main test file (test_generated.py).
        """
        logger.info("🧪 Generating Test File...")
        
        test_cases = self.test_plan.get("test_cases", [])
        start_url = self.test_plan.get("start_url", "")
        
        # Fill the prompt template
        prompt = TEST_FILE_PROMPT.format(
            start_url=start_url,
            test_cases_info=json.dumps(test_cases, indent=2),
            page_objects_map=json.dumps(page_class_map, indent=2)
        )
        
        # Ask AI to generate the code
        code = self.llm.chat([{"role": "user", "content": prompt}])
        code = self._clean_code_markdown(code)
        
        # Add necessary imports for the Page Objects we just created
        imports = "import pytest\nfrom playwright.sync_api import Page, expect\n"
        for class_name in page_class_map.values():
            module_name = self._to_snake_case(class_name)
            imports += f"from pages.{module_name} import {class_name}\n"
            
        final_code = imports + "\n" + code
        
        self._save_file(self.tests_dir, "test_generated.py", final_code)

    def _generate_conftest(self):
        """
        Generates 'conftest.py' for pytest configuration.
        Sets up the browser viewport.
        """
        content = """import pytest
from playwright.sync_api import sync_playwright

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

    def _validate_and_fix_code(self, code: str, max_retries: int = 2) -> str:
        """
        Self-Correction Mechanism.
        Checks if the generated code has syntax errors. If so, asks AI to fix it.
        """
        for attempt in range(max_retries + 1):
            try:
                ast.parse(code)
                return code # Code is valid!
            except SyntaxError as e:
                logger.warning(f"⚠️ Syntax error detected: {e}. Attempting fix ({attempt+1}/{max_retries})...")
                
                if attempt == max_retries:
                    logger.error("❌ Failed to fix syntax error after retries.")
                    return code # Return broken code as last resort
                
                # Ask AI to fix the specific error
                prompt = FIX_SYNTAX_PROMPT.format(error_message=str(e), code=code)
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

    def _to_snake_case(self, name: str) -> str:
        """Converts CamelCase to snake_case (e.g., HomePage -> home_page)."""
        return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

    def _save_file(self, directory: str, filename: str, content: str):
        """Helper to save content to a file."""
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
