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
    
    def generate_tests(self, plan_path: str) -> bool:
        """Generate tests from plan."""
        try:
            generator = CodeGenerator(plan_path, str(self.output_dir))
            generator.generate()
            return True
        except Exception as e:
            print(f"Error generating tests: {e}")
            return False
    
    def run_tests(self) -> Dict:
        """Run generated tests using pytest."""
        import os
        original_dir = Path.cwd()
        
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
                [sys.executable, "-m", "pytest", "tests", "-v", "--tb=short", "--color=yes"],
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
    
    def _parse_pytest_output(self, stdout: str, stderr: str) -> List[Dict]:
        """Parse pytest output to extract test results."""
        results = []
        
        print(f"[DEBUG] Parsing pytest output...")
        print(f"[DEBUG] First 500 chars of stdout:\n{stdout[:500]}")
        
        # Pattern to match test results: test_file.py::test_name PASSED/FAILED
        # Also handle patterns with or without color codes
        pattern = r'(test_\w+\.py)::(test_\w+)\s+(?:\x1b\[\d+m)?(PASSED|FAILED)'
        
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
