import json
import os
import ast
import re
from typing import Dict, List, Any
from loguru import logger
from src.agent.llm.ollama_client import LLMClient
from src.generators.prompts import (
    PAGE_OBJECT_PROMPT,
    FIX_SYNTAX_PROMPT,
    SINGLE_TEST_FILE_PROMPT,
    VALIDATE_PAGE_OBJECT_PROMPT,
    VALIDATE_TEST_FILE_PROMPT
)

class CodeGenerator:
    """
    Generates Playwright test code (Page Objects and Test Files) from a Test Plan.
    """
    
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
        
        # Initialize the AI client (using DeepSeek Coder for code generation)
        # Use generator-specific settings so other phases using LLMClient aren't affected.
        self.llm = LLMClient(
            model="deepseek-coder-v2:16b",
            config={
                "temperature": 0.2,
                # Allow larger outputs for full files.
                "max_tokens": 4096,
                # Increase context window so the model can see more prompt/test-plan details.
                "num_ctx": 8192,
                # Encourage longer completions on Ollama (maps to generation length).
                "num_predict": 4096,
            },
        )
        
        # Load the test plan data
        self.test_plan = self._load_test_plan()
        self.pages = self.test_plan.get("pages", {})
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
        
        self.generate_page_objects()
        self.generate_test_files()
        self._generate_conftest()
        
        logger.info(f"✅ Code generation complete! Check folder: {self.output_dir}")

    def generate_page_objects(self) -> Dict[str, str]:
        """Generates Page Object Models."""
        logger.info("📄 Generating Page Objects...")
        
        # Step 1: Create the base class for all Page Objects
        self._generate_base_page()
        
        # Step 2: Organize test plan data by Page ID
        pages_data = self._group_data_by_page()
        
        # Step 3: Generate a Page Object file for each page found
        page_class_map = {}
        for page_id, data in pages_data.items():
            class_name = self._generate_page_object(page_id, data)
            page_class_map[page_id] = class_name
            
        self.page_class_map = page_class_map
        
        # Step 4: Validate and fix Page Objects (Iteration Phase)
        logger.info("🔄 Validation Phase: Checking Page Objects...")
        self._validate_and_fix_page_objects(pages_data)
        
        return page_class_map

    def generate_test_files(self):
        """Generates Test Files (one per test case)."""
        logger.info("🧪 Generating Test Files...")
        
        if not hasattr(self, 'page_class_map'):
             logger.warning("Page class map not found. Assuming Page Objects exist but map is empty. This might fail.")
             self.page_class_map = {}

        test_cases = self.test_plan.get("test_cases", [])
        
        for test_case in test_cases:
            self._generate_single_test_file(test_case, self.page_class_map)

    def _validate_and_fix_page_objects(self, pages_data: Dict[str, Dict]):
        """
        Validates Page Objects and fixes placeholder selectors.
        """
        for page_id, data in pages_data.items():
            class_name = self.page_class_map[page_id]
            filename = self._to_snake_case(class_name) + ".py"
            filepath = os.path.join(self.pages_dir, filename)
            
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
            
            # Check for placeholder selectors
            if "best_locator" in code or "another_best_locator" in code or "yet_another_best_locator" in code:
                logger.warning(f"⚠️ Found placeholder selectors in {filename}. Fixing...")
                
                # Get selectors for this page
                selectors_info = json.dumps(data["elements"], indent=2)
                
                prompt = VALIDATE_PAGE_OBJECT_PROMPT.format(
                    page_object_code=code,
                    expected_selectors=selectors_info
                )
                if self.feedback and not self.feedback.startswith("No specific feedback"):
                    prompt = prompt + "\n\nUser Feedback (apply when fixing page object):\n" + self.feedback
                fixed_code = self.llm.chat([{"role": "user", "content": prompt}])
                fixed_code = self._clean_code_markdown(fixed_code)
                fixed_code = self._validate_and_fix_code(fixed_code)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                
                logger.info(f"✅ Fixed {filename}")
    
    def _validate_and_fix_single_test(self, filename: str, page_objects_info: Dict):
        """
        Validates a single test file and fixes method calls that don't exist.
        """
        filepath = os.path.join(self.tests_dir, filename)
        
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        
        # Extract all method calls that look like page_object.method()
        # Simple regex: word.word(
        method_calls = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\(', code)
        
        # Check if any called methods don't exist in our Page Objects
        needs_fix = False
        for call in method_calls:
            # Extract method name (everything after the dot, before the paren)
            method_name = call.split('.')[1].replace('(', '')
            
            # Skip common Playwright methods
            if method_name in ['goto', 'fill', 'click', 'locator', 'get_by_role', 'get_by_text', 'to_have_url']:
                continue
            
            # Check if this method exists in any of our Page Objects
            found = False
            for po_class, po_info in page_objects_info.items():
                for method_sig in po_info.get("methods", []):
                    if method_sig.startswith(method_name + "("):
                        found = True
                        break
                if found:
                    break
            
            if not found and method_name not in ['navigate', 'get_title']:  # Base class methods
                logger.warning(f"⚠️ Method '{method_name}' not found in Page Objects. Fixing {filename}...")
                needs_fix = True
                break
        
        if needs_fix:
            prompt = VALIDATE_TEST_FILE_PROMPT.format(
                test_code=code,
                page_objects_methods=json.dumps(page_objects_info, indent=2)
            )
            
            fixed_code = self.llm.chat([{"role": "user", "content": prompt}])
            fixed_code = self._clean_code_markdown(fixed_code)
            
            # Re-strip imports and add them back
            fixed_code = self._strip_import_lines(fixed_code)
            fixed_code = self._remove_page_fixture_if_present(fixed_code)
            
            imports = "import pytest\nfrom playwright.sync_api import Page, expect\n"
            for class_name in self.page_class_map.values():
                module_name = self._to_snake_case(class_name)
                imports += f"from pages.{module_name} import {class_name}\n"
            
            fixed_code = imports + "\n" + fixed_code
            fixed_code = self._validate_and_fix_code(fixed_code)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(fixed_code)
            
            logger.info(f"✅ Fixed {filename}")
    
    def _extract_page_object_methods(self, page_id: str) -> List[str]:
        """
        Extracts method names and signatures from a Page Object file.
        """
        class_name = self.page_class_map.get(page_id)
        if not class_name:
            return []
        
        filename = self._to_snake_case(class_name) + ".py"
        filepath = os.path.join(self.pages_dir, filename)
        
        if not os.path.exists(filepath):
            return []
        
        with open(filepath, "r", encoding="utf-8") as f:
            code = f.read()
        
        try:
            tree = ast.parse(code)
            methods = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                            # Extract method signature
                            args = [arg.arg for arg in item.args.args if arg.arg != "self"]
                            method_sig = f"{item.name}({', '.join(args)})"
                            methods.append(method_sig)
            
            return methods
        except:
            return []

    def _generate_base_page(self):
        """
        Creates 'base_page.py'.
        This class holds common methods used by all pages (like navigation).
        Only creates if file doesn't exist to preserve custom modifications.
        """
        # Skip if file already exists
        if os.path.exists(os.path.join(self.pages_dir, "base_page.py")):
            logger.info("⏭️  Skipping base_page.py (already exists)")
            return
            
        content = """from playwright.sync_api import Page


class BasePage:
    \"\"\"Base class for all Page Objects.\"\"\"

    # Override this in subclasses if the page has a specific URL
    URL = None

    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str | None = None):
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
        
        # Determine a class name (always derived from page_id to avoid ambiguous naming)
        class_name = f"{page_id.capitalize()}Page"
        
        # Get URL if this is the home page (page_0)
        # page_url = self.test_plan.get("start_url") if page_id == "page_0" else None
        page_url = self.pages.get(page_id, {}).get("url")
        if not page_url and page_id == "page_0":
            page_url = self.test_plan.get("start_url")
        
        # Fill the prompt template
        prompt = PAGE_OBJECT_PROMPT.format(
            page_name=f"Page associated with ID {page_id}",
            page_id=page_id,
            page_url=page_url or "Not specified",
            elements_info=elements_json,
            actions_info=actions_list,
            class_name=class_name
        )
        
        if self.feedback and not self.feedback.startswith("No specific feedback"):
            prompt += f"\n\nUser Feedback (apply to Page Object generation):\n{self.feedback}"
        
        # Ask AI to generate the code
        code = self.llm.chat([{"role": "user", "content": prompt}])
        
        # Clean and validate the code
        code = self._clean_code_markdown(code)
        code = self._validate_and_fix_code(code)
        
        # Save to file (convert ClassName to snake_case_filename.py)
        filename = self._to_snake_case(class_name) + ".py"
        self._save_file(self.pages_dir, filename, code)
            
        return class_name

    def _generate_single_test_file(self, test_case: Dict, page_class_map: Dict[str, str]):
        """
        Generates a single test file for a test case.
        """
        test_id = test_case.get("id", "unknown_test")
        logger.info(f"🧪 Generating Test File for {test_id}...")
        
        start_url = self.test_plan.get("start_url", "")
        
        # Gather Page Object methods info
        page_objects_info = {}
        for page_id, class_name in page_class_map.items():
            methods = self._extract_page_object_methods(page_id)
            page_objects_info[class_name] = {
                "page_id": page_id,
                "methods": methods
            }
        
        # Fill the prompt template
        prompt = SINGLE_TEST_FILE_PROMPT.format(
            start_url=start_url,
            test_case_info=json.dumps(test_case, indent=2),
            page_objects_info=json.dumps(page_objects_info, indent=2),
            feedback=self.feedback
        )
        
        # Ask AI to generate the code
        code = self.llm.chat([{"role": "user", "content": prompt}])
        code = self._clean_code_markdown(code)

        # Defensive cleanup
        code = self._strip_import_lines(code)
        code = self._remove_page_fixture_if_present(code)
        
        # Add necessary imports for the Page Objects we just created
        imports = "import pytest\nfrom playwright.sync_api import Page, expect\n"
        for class_name in page_class_map.values():
            module_name = self._to_snake_case(class_name)
            imports += f"from pages.{module_name} import {class_name}\n"
            
        final_code = imports + "\n" + code

        # Validate and attempt to fix syntax issues
        final_code = self._validate_and_fix_code(final_code)
        
        filename = f"test_{test_id.lower()}.py"
        self._save_file(self.tests_dir, filename, final_code)
        
        # Iteration Phase: Validate the test uses correct Page Object methods
        logger.info(f"🔄 Validation Phase: Checking {filename}...")
        self._validate_and_fix_single_test(filename, page_objects_info)

    def _strip_import_lines(self, code: str) -> str:
        lines = []
        for line in code.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                continue
            lines.append(line)
        return "\n".join(lines).lstrip()

    def _remove_page_fixture_if_present(self, code: str) -> str:
        """Remove an accidentally generated `page` fixture block (common LLM mistake)."""
        lines = code.splitlines()
        out: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip().startswith("@pytest.fixture"):
                # Look ahead for a `def page(` right after the decorator(s)
                j = i
                while j < len(lines) and lines[j].strip().startswith("@"):  # decorators
                    j += 1
                if j < len(lines) and lines[j].lstrip().startswith("def page("):
                    # Skip until we hit a non-indented line (next top-level stmt)
                    j += 1
                    while j < len(lines):
                        nxt = lines[j]
                        if nxt.strip() == "":
                            j += 1
                            continue
                        if not nxt.startswith(" ") and not nxt.startswith("\t"):
                            break
                        j += 1
                    i = j
                    continue
            out.append(line)
            i += 1
        return "\n".join(out).lstrip()

    def _generate_conftest(self):
        """
        Generates 'conftest.py' for pytest configuration.
        Sets up the browser viewport.
        Only creates if file doesn't exist to preserve custom modifications like monkey patching.
        """
        # Skip if file already exists
        if os.path.exists(os.path.join(self.tests_dir, "conftest.py")):
            logger.info("⏭️  Skipping conftest.py (already exists)")
            return
            
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

    def _validate_and_fix_code(self, code: str, max_retries: int = 6) -> str:
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
