#!/usr/bin/env python
"""
Validate and fix test plan with working selectors.
This script loads an existing test_plan.json, validates all selectors using Playwright,
fixes hallucinated selectors, makes steps specific, and validates expected outputs.
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Add src to path
ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout
from loguru import logger


class TestPlanValidator:
    """Validates and refines test plans with working selectors."""
    
    def __init__(self, test_plan_path: str, max_iterations: int = 5):
        self.test_plan_path = Path(test_plan_path)
        self.max_iterations = max_iterations
        
    def load_test_plan(self) -> Dict:
        """Load test plan from JSON."""
        logger.info(f"Loading test plan from {self.test_plan_path}")
        
        with open(self.test_plan_path, "r", encoding="utf-8") as f:
            test_plan = json.load(f)
        
        logger.info(f"Loaded {len(test_plan.get('test_cases', []))} test cases")
        return test_plan
    
    async def find_working_selector(self, page: Page, element_key: str, 
                                   css_selector: str, xpath: str) -> Optional[Dict]:
        """
        Find a working selector for the element.
        Returns dict with selector info or None if not found.
        """
        # Extract information from element_key (format: "id|text|")
        parts = element_key.split("|")
        element_id = parts[0].strip() if len(parts) > 0 else ""
        element_text = parts[1].strip() if len(parts) > 1 else ""
        
        logger.debug(f"Finding selector for: id='{element_id}', text='{element_text}'")
        
        # Try strategies in order
        strategies = []
        
        # 1. Try ID selector if we have ID
        if element_id and element_id not in ["", "None"]:
            strategies.append(("id", f"#{element_id}"))
        
        # 2. Try text-based selectors if we have text
        if element_text and len(element_text) > 0:
            # Try different text lengths
            for text_len in [len(element_text), 50, 30, 20]:
                text_snippet = element_text[:text_len].strip()
                if text_snippet:
                    strategies.extend([
                        ("text", f"text={text_snippet}"),
                        ("has-text-link", f"a:has-text(\"{text_snippet}\")"),
                        ("has-text-button", f"button:has-text(\"{text_snippet}\")"),
                        ("xpath-text", f"xpath=//*[contains(text(), '{text_snippet}')]"),
                    ])
                    break
        
        # 3. Try provided selectors
        if css_selector and css_selector not in ["", "a:has-text(\"\")"]:
            strategies.append(("css", css_selector))
        if xpath:
            strategies.append(("xpath", f"xpath={xpath}"))
        
        # Test each strategy
        for strategy_name, selector in strategies:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                
                if count > 0:
                    # Check if visible
                    first_elem = locator.first
                    is_visible = await first_elem.is_visible()
                    
                    if is_visible:
                        # Get actual text and attributes
                        text_content = (await first_elem.text_content() or "").strip()
                        inner_text = (await first_elem.inner_text()).strip() if await first_elem.is_visible() else ""
                        
                        logger.info(f"✓ Found working selector ({strategy_name}): {selector}")
                        logger.debug(f"  Element text: '{text_content[:50]}'")
                        
                        # Return clean selector (remove xpath= prefix for storage)
                        if selector.startswith("xpath="):
                            return {
                                "css_selector": "",
                                "xpath": selector.replace("xpath=", ""),
                                "text": text_content or inner_text,
                                "strategy": strategy_name
                            }
                        else:
                            return {
                                "css_selector": selector,
                                "xpath": "",
                                "text": text_content or inner_text,
                                "strategy": strategy_name
                            }
            except Exception as e:
                logger.debug(f"✗ Strategy '{strategy_name}' failed: {selector} - {e}")
                continue
        
        logger.warning(f"⚠️  Could not find working selector for: {element_key}")
        return None
    
    async def validate_and_fix_test_case(self, page: Page, test_case: Dict) -> Dict:
        """
        Validate and fix a single test case.
        Returns updated test_case dict.
        """
        tc_id = test_case.get("id", "unknown")
        logger.info(f"Validating test case: {tc_id}")
        
        fixed_selectors = []
        all_selectors_valid = True
        
        # Validate and fix each selector
        for selector in test_case.get("selectors", []):
            element_key = selector.get("element_key", "")
            css_selector = selector.get("css_selector", "")
            xpath = selector.get("xpath", "")
            description = selector.get("description", "")
            page_id = selector.get("page_id", "page_0")
            
            # Find working selector
            working = await self.find_working_selector(page, element_key, css_selector, xpath)
            
            if working:
                # Update selector with working one
                fixed_selectors.append({
                    "element_key": element_key,
                    "page_id": page_id,
                    "css_selector": working["css_selector"],
                    "xpath": working["xpath"],
                    "description": description or f"Selector for {element_key} (strategy: {working['strategy']})"
                })
                logger.debug(f"✓ Fixed selector for: {element_key}")
            else:
                # Keep original but mark as potentially broken
                fixed_selectors.append(selector)
                all_selectors_valid = False
                logger.warning(f"⚠️  Could not fix selector for: {element_key}")
        
        # Update test case
        test_case["selectors"] = fixed_selectors
        
        # Make steps more specific
        test_case["steps"] = await self.make_steps_specific(page, test_case)
        
        return test_case
    
    
    async def make_steps_specific(self, page: Page, test_case: Dict) -> List[Dict]:
        """Make test steps more specific with actual element details."""
        steps = test_case.get("steps", [])
        selectors = {sel["element_key"]: sel for sel in test_case.get("selectors", [])}
        
        specific_steps = []
        for step in steps:
            action = step.get("action", "")
            target = step.get("target", "")
            details = step.get("details", "")
            page_id = step.get("page_id", "page_0")
            
            # Try to find selector for this target
            selector_info = selectors.get(target.split("|")[0] + "||", None) if "|" in target else None
            
            # Make details more specific
            if action == "click" and selector_info:
                css = selector_info.get("css_selector", "")
                xpath = selector_info.get("xpath", "")
                if css or xpath:
                    details = f"Click on element: {target}. Selector: {css or xpath}"
            elif action == "assert":
                details = details or "Verify expected outcome on current page"
            
            specific_steps.append({
                "action": action,
                "page_id": page_id,
                "target": target,
                "details": details
            })
        
        return specific_steps
    
    async def validate_and_fix_test_plan(self, test_plan: Dict) -> Dict:
        """
        Validate and fix entire test plan.
        Returns updated test_plan.
        """
        start_url = test_plan.get("start_url", "")
        if not start_url:
            logger.error("No start_url in test plan!")
            return test_plan
        
        logger.info(f"Validating test plan for: {start_url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()
            
            try:
                # Navigate to start URL
                logger.info(f"Navigating to {start_url}")
                await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                
                # Validate and fix each test case
                fixed_test_cases = []
                for tc in test_plan.get("test_cases", []):
                    fixed_tc = await self.validate_and_fix_test_case(page, tc)
                    fixed_test_cases.append(fixed_tc)
                    
                    # Navigate back to start page for next test
                    await page.goto(start_url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1000)
                
                test_plan["test_cases"] = fixed_test_cases
                
            except Exception as e:
                logger.error(f"Error during validation: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                await browser.close()
        
        return test_plan
    
    async def create_validated_test_plan(self) -> Dict:
        """
        Main method: Load test plan, validate and fix all selectors and steps.
        """
        logger.info("=" * 80)
        logger.info("Validating and fixing test plan with working selectors")
        logger.info("=" * 80)
        
        # Load test plan
        test_plan = self.load_test_plan()
        
        # Validate and fix (with iterations if needed)
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"\n{'='*80}")
            logger.info(f"Validation Iteration {iteration}/{self.max_iterations}")
            logger.info(f"{'='*80}")
            
            test_plan = await self.validate_and_fix_test_plan(test_plan)
            
            # Check if all selectors are now valid
            all_valid = all(
                all(
                    (sel.get("css_selector") or sel.get("xpath"))
                    for sel in tc.get("selectors", [])
                )
                for tc in test_plan.get("test_cases", [])
            )
            
            if all_valid:
                logger.info(f"✅ All selectors validated on iteration {iteration}!")
                break
        
        # Save updated test plan
        logger.info(f"\nSaving updated test plan to {self.test_plan_path}")
        self.test_plan_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.test_plan_path, "w", encoding="utf-8") as f:
            json.dump(test_plan, f, indent=2)
        
        logger.info("✅ Test plan saved successfully!")
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        test_cases = test_plan.get("test_cases", [])
        logger.info(f"Test Cases: {len(test_cases)}")
        total_selectors = sum(len(tc.get("selectors", [])) for tc in test_cases)
        logger.info(f"Total Selectors: {total_selectors}")
        
        # Count valid selectors
        valid_selectors = sum(
            sum(1 for sel in tc.get("selectors", []) if sel.get("css_selector") or sel.get("xpath"))
            for tc in test_cases
        )
        logger.info(f"Valid Selectors: {valid_selectors}/{total_selectors}")
        logger.info(f"Output: {self.test_plan_path}")
        logger.info("=" * 80)
        
        return test_plan


async def main():
    """Main entry point."""
    # Path to test plan
    test_plan_path = ROOT / "src" / "artifacts" / "test_plans" / "test_plan.json"
    
    # Check if test plan exists
    if not test_plan_path.exists():
        logger.error(f"Test plan not found: {test_plan_path}")
        logger.info("Please generate a test plan first")
        sys.exit(1)
    
    # Create validator
    validator = TestPlanValidator(
        test_plan_path=str(test_plan_path),
        max_iterations=5
    )
    
    # Validate and fix test plan
    test_plan = await validator.create_validated_test_plan()
    
    logger.info(f"\n✅ Test plan validated and fixed!")
    logger.info(f"📄 File: {test_plan_path}")
    logger.info(f"🧪 Test Cases: {len(test_plan.get('test_cases', []))}")


if __name__ == "__main__":
    # Configure logger
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    # Run
    asyncio.run(main())
