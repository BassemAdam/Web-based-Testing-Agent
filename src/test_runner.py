"""
Test Runner Module
Handles test generation and execution.
"""
import subprocess
import sys
import json
import re
from pathlib import Path
from typing import Dict, List

from generators.code_generator import CodeGenerator


class TestRunner:
    """Manages test generation and execution."""
    
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.output_dir = root_path / "artifacts" / "generated_tests"
    
    def generate_tests(self, plan_path: str, feedback: str = None, test_filename: str = None) -> bool:
        """Generate tests from plan."""
        try:
            generator = CodeGenerator(plan_path, str(self.output_dir), feedback=feedback)
            generator.generate(feedback=feedback, test_filename=test_filename)
            return True
        except Exception as e:
            print(f"Error generating tests: {e}")
            return False
    
    def run_tests(self, plan_path: str = None, selfheal: bool = False) -> Dict:
        """
        Run generated tests using pytest.
        
        Args:
            plan_path: Path to the test plan JSON file (required for self-healing)
                      Defaults to src/artifacts/test_plans/test_plan.json
            selfheal: If True, automatically regenerate failed tests with error feedback
        
        Returns:
            Dictionary containing test results and execution details
        """
        import os
        original_dir = Path.cwd()
        
        # Set default plan path if not provided
        if plan_path is None:
            plan_path = str(self.root_path / "src" / "artifacts" / "test_plans" / "test_plan.json")
            print(f"[DEBUG] Using default plan path: {plan_path}")
        
        # Check if tests directory exists
        tests_dir = self.output_dir / "tests"
        if not tests_dir.exists():
            return {
                "success": False,
                "results": [],
                "stdout": "",
                "stderr": f"Tests directory not found at: {tests_dir}\nPlease generate tests first.",
                "return_code": -1,
            }
        
        try:
            # Change to generated tests directory (like run_tests.py does)
            os.chdir(str(self.output_dir))
            print(f"[DEBUG] Changed directory to: {self.output_dir}")
            print(f"[DEBUG] Running pytest from: {os.getcwd()}")
            
            # Run pytest with verbose output and color
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests", "-v", "--tb=short", "--color=yes", 
                 "--headed", "--slowmo", "1000"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            print(f"[DEBUG] Pytest return code: {result.returncode}")
            print(f"[DEBUG] Stdout length: {len(result.stdout)}")
            print(f"[DEBUG] Stderr length: {len(result.stderr)}")
            
            # Parse the output
            test_results = self._parse_pytest_output(result.stdout, result.stderr)
            print(f"[DEBUG] Parsed {len(test_results)} test results")
            
            # Collect screenshots for each test
            self._collect_screenshots(test_results)
            
            # Self-healing: regenerate failed tests with error feedback
            if selfheal :
                failed_tests = [t for t in test_results if t["status"] == "FAILED"]
                if failed_tests:
                    print(f"\n[SELF-HEAL] Found {len(failed_tests)} failed test(s). Attempting to regenerate with error feedback...")
                    
                    for failed_test in failed_tests:
                        test_filename = failed_test["file"]
                        failure_reason = failed_test.get("reason", "Test failed - no error details available")
                        
                        print(f"\n[SELF-HEAL] Regenerating {test_filename} with feedback:")
                        print(f"[SELF-HEAL] Error: {failure_reason}...")
                        
                        # Build feedback message with error context
                        feedback = f"""The test failed with the following error:

                        {failure_reason}

                        Please fix the test by:
                        1. Analyzing the error message carefully
                        2. If it's a locator issue (strict mode violation, element not found), use more specific locators or add .nth(0) it solves alot of issues as needed
                        3. If it's a timing issue, add appropriate waits
                        4. If it's an assertion issue, adjust the expected values or conditions
                        5. Ensure the test follows Playwright best practices

                        Generate a corrected version of this test."""
                        
                        print(f"[SELF-HEAL] test_filename: {test_filename}")
                        
                        # Regenerate the specific test file
                        success = self.generate_tests(
                            plan_path=plan_path,
                            feedback=feedback,
                            test_filename=test_filename
                        )
                        
                        if success:
                            print(f"[SELF-HEAL] ✓ Successfully regenerated {test_filename}")
                        else:
                            print(f"[SELF-HEAL] ✗ Failed to regenerate {test_filename}")
                    
                    print(f"\n[SELF-HEAL] Self-healing complete. {len(failed_tests)} test(s) regenerated.")
                    print("[SELF-HEAL] Run tests again to verify the fixes.")
            elif selfheal :
                print("\n[SELF-HEAL] Warning: Self-healing enabled but no plan_path provided. Skipping self-healing.")
            
            return {
                "success": result.returncode == 0,
                "results": test_results,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "results": [],
                "stdout": "",
                "stderr": "Test execution timed out after 5 minutes",
                "return_code": -1,
            }
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            return {
                "success": False,
                "results": [],
                "stdout": "",
                "stderr": f"Error running tests: {str(e)}\n\n{error_details}",
                "return_code": -1,
            }
        finally:
            os.chdir(str(original_dir))
    
    def _collect_screenshots(self, test_results: List[Dict]):
        """Collect screenshots for each test case."""
        screenshot_base = self.output_dir / "screenshots"
        
        if not screenshot_base.exists():
            print("[DEBUG] No screenshots directory found")
            return
        
        for result in test_results:
            # Use test_id instead of test_name - directories are named by test ID (e.g., tc_signin_valid_01)
            test_id = result["test_id"]
            screenshot_dir = screenshot_base / test_id
            
            # If exact match doesn't exist, try to find a directory that starts with the test ID
            # This handles cases where the directory might have a suffix like 'chromium'
            if not screenshot_dir.exists():
                candidates = list(screenshot_base.glob(f"{test_id}*"))
                if candidates:
                    screenshot_dir = candidates[0]
            
            if screenshot_dir.exists():
                screenshots = sorted(screenshot_dir.glob("*.png"))
                result["screenshots"] = [str(s) for s in screenshots]
                result["screenshot_count"] = len(screenshots)
                print(f"[DEBUG] Found {len(screenshots)} screenshots for {test_id}")
            else:
                result["screenshots"] = []
                result["screenshot_count"] = 0
    
    def _parse_pytest_output(self, stdout: str, stderr: str) -> List[Dict]:
        """Parse pytest output to extract test results."""
        results = []
        
        print(f"[DEBUG] Parsing pytest output...")
        print(f"[DEBUG] First 500 chars of stdout:\n{stdout[:500]}")
        
        # Pattern to match test results with ANSI color codes and browser markers
        # Format: tests/test_file.py::test_name[chromium] [31mFAILED[0m
        pattern = r'(test_\w+\.py)::(test_\w+)(?:\[[\w-]+\])?\s+(?:\x1b\[\d+m)?(PASSED|FAILED)(?:\x1b\[\d+m)?'
        
        matches = list(re.finditer(pattern, stdout))
        print(f"[DEBUG] Found {len(matches)} test result matches")
        
        for match in matches:
            file_name = match.group(1)
            test_name = match.group(2)
            status = match.group(3)
            
            print(f"[DEBUG] Parsed test: {file_name}::{test_name} -> {status}")
            
            # Extract test ID from test name (e.g., test_tc_signin_valid_01 -> tc_signin_valid_01)
            test_id = test_name.replace("test_", "")
            
            result = {
                "test_id": test_id,
                "test_name": test_name,
                "file": file_name,
                "status": status,
                "reason": None,
                "duration": None,
                "screenshots": [],
                "screenshot_count": 0,
            }
            
            # Try to extract failure reason if failed
            if status == "FAILED":
                # Look for the failure section after this test
                failure_pattern = rf'{re.escape(test_name)}.*?(?:AssertionError|Error|Exception):\s*(.+?)(?=\n\n|\n_+|$)'
                failure_match = re.search(failure_pattern, stdout + "\n" + stderr, re.DOTALL)
                if failure_match:
                    reason = failure_match.group(1).strip()[:300]  # Limit length
                    result["reason"] = reason
                else:
                    # Try alternative pattern for short failures
                    short_pattern = rf'{re.escape(test_name)}.*?FAILED.*?\n(.+?)(?=\n\n|$)'
                    short_match = re.search(short_pattern, stdout, re.DOTALL)
                    if short_match:
                        result["reason"] = short_match.group(1).strip()[:300]
                    else:
                        result["reason"] = "Test failed - check full output for details"
            
            results.append(result)
        
        # If no results found, check if there are any error messages
        if not results:
            print("[DEBUG] No test results found, checking for errors...")
            if "ERROR" in stdout or "ERROR" in stderr:
                print("[DEBUG] Found ERROR in output")
            if "collected 0 items" in stdout:
                print("[DEBUG] No tests were collected")
        
        return results
    
    def save_plan(self, plan: Dict, filename: str = "test_plan.json") -> str:
        """Save test plan to JSON file."""
        plan_path = self.root_path / "src" / "artifacts" / "test_plans" / filename
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, default=lambda o: o.__dict__)
        
        return str(plan_path)
  
    # def refine_test_file(self, file_path: str, feedback: str, model_name: str = None) -> bool:
    #     """
    #     Refine a single test file based on feedback.
        
    #     Args:
    #         file_path: Path to the test file to refine
    #         feedback: User feedback to apply
    #         model_name: Optional model name override
            
#         Returns:
#             True if successful, False otherwise
#         """
#         try:
#             from src.agent.llm.ollama_client import CopilotClient
            
#             # Read current file content
#             with open(file_path, "r", encoding="utf-8") as f:
#                 current_code = f.read()
            
#             # Build refinement prompt
#             prompt = f"""You are an expert test automation engineer. 
# Refine the following Playwright test code based on the user's feedback.

# CURRENT CODE:
# ```python
# {current_code}
# ```

# USER FEEDBACK:
# {feedback}

# REQUIREMENTS:
# 1. Apply the user's feedback to improve the test code
# 2. Maintain the same test structure and naming
# 3. Keep all existing functionality unless explicitly asked to change
# 4. Use Playwright best practices (explicit waits, proper assertions)
# 5. Return ONLY the complete updated Python code, no explanations

# OUTPUT:
# Return the complete updated Python file content."""

#             # Call LLM
#             client = CopilotClient(model=model_name or "gpt-4o")
#             response = client.chat([
#                 {"role": "system", "content": "You are an expert Playwright test automation engineer."},
#                 {"role": "user", "content": prompt}
#             ])
            
#             # Extract code from response
#             refined_code = response.strip()
#             if refined_code.startswith("```python"):
#                 refined_code = refined_code[9:]
#             if refined_code.startswith("```"):
#                 refined_code = refined_code[3:]
#             if refined_code.endswith("```"):
#                 refined_code = refined_code[:-3]
#             refined_code = refined_code.strip()
            
#             # Validate it's valid Python
#             import ast
#             ast.parse(refined_code)
            
#             # Write back to file
#             with open(file_path, "w", encoding="utf-8") as f:
#                 f.write(refined_code)
            
#             return True
            
#         except Exception as e:
#             print(f"Error refining {file_path}: {e}")
#             return False
