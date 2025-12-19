from __future__ import annotations
import json
from typing import Dict, List, Optional

from ..llm.ollama_client import LLMClient
from ..models.site_graph import SiteGraph
from ..models.test_case import TestCase, TestStep, SelectorInfo
from ..utils.keys import build_element_key, canonicalize_key

class MultiPageTestDesignPipeline:
    """
    Given a SiteGraph (multiple pages + edges),
    propose HIGH-LEVEL multi-page test cases.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model=model_name)

    def _build_element_lookup(self, graph: SiteGraph) -> Dict[str, Dict]:
        """
        Build a lookup with enhanced selector information.
        """
        lookup = {}
        for page_id, node in graph.pages.items():
            for e in node.snapshot.elements:
                # Include name and type for inputs to make keys unique
                key = build_element_key(
                    e.tag, 
                    e.text, 
                    e.id,
                    name=e.name if e.tag == "input" else None,
                    input_type=e.type if e.tag == "input" else None
                )
                full_key = f"{page_id}::{key}"
                
                # Build a playwright-style locator recommendation
                playwright_locator = self._recommend_playwright_locator(e)
                
                lookup[full_key] = {
                    "element_key": key,
                    "page_id": page_id,
                    "css_selector": e.css_selector,
                    "xpath": e.xpath,
                    "playwright_locator": playwright_locator,
                    "description": e.short_description(),
                    "element": e,
                }
        return lookup
    def _recommend_playwright_locator(self, element) -> str:
        """
        Recommend the best Playwright locator strategy for an element.
        Priority: data-testid > id > name > aria-label > placeholder > type+context > href > text > class
        """
        attrs = element.attributes or {}
        
        # 1. data-testid (most reliable - specifically for testing)
        data_testid = attrs.get("data-testid") or attrs.get("data-test") or attrs.get("data-cy")
        if data_testid:
            return f"page.get_by_test_id('{data_testid}')"
        
        # 2. ID (very reliable if present and meaningful)
        if element.id and not self._is_generated_id(element.id):
            return f"page.locator('#{element.id}')"
        
        # 3. name attribute (great for form inputs)
        if element.name and element.tag in ["input", "select", "textarea"]:
            return f"page.locator('{element.tag}[name=\"{element.name}\"]')"
        
        # 4. aria-label (accessible and stable)
        if element.aria_label:
            return f"page.get_by_label('{element.aria_label}')"
        
        # 5. placeholder (for inputs)
        placeholder = attrs.get("placeholder")
        if placeholder and element.tag == "input":
            return f"page.get_by_placeholder('{placeholder}')"
        
        # 6. type attribute combined with context (for inputs)
        input_type = element.type
        if element.tag == "input" and input_type in ["email", "password", "search", "tel"]:
            # Use type as primary identifier - more specific than just class
            return f"page.locator('input[type=\"{input_type}\"]')"
        
        # 7. href for links (very reliable)
        href = attrs.get("href")
        if element.tag == "a" and href and self._is_meaningful_href(href):
            # Escape quotes in href
            safe_href = href.replace('"', '\\"')
            return f"page.locator('a[href=\"{safe_href}\"]')"
        
        # 8. get_by_role with name for buttons and links with text
        if element.tag in ["button", "a"] and element.text:
            role = "link" if element.tag == "a" else "button"
            text = element.text.strip()[:50]
            if text and len(text) > 1:
                # Escape single quotes
                safe_text = text.replace("'", "\\'")
                return f"page.get_by_role('{role}', name='{safe_text}')"
        
        # 9. Text content for other elements
        if element.text and len(element.text.strip()) < 50 and len(element.text.strip()) > 1:
            safe_text = element.text.strip().replace("'", "\\'")
            return f"page.get_by_text('{safe_text}')"
        
        # 10. Specific/semantic classes (filter out utility classes)
        specific_classes = self._get_specific_classes(element.classes)
        if specific_classes:
            class_selector = ".".join(specific_classes[:2])
            return f"page.locator('{element.tag}.{class_selector}')"
        
        # 11. Fallback to CSS selector if it's specific enough
        if element.css_selector and self._is_specific_selector(element.css_selector):
            return f"page.locator('{element.css_selector}')"
        
        # 12. Last resort - tag with nth-child would need parent context
        return f"page.locator('{element.tag}')"

    def _is_generated_id(self, id_value: str) -> bool:
        """Check if an ID looks auto-generated (not reliable for testing)."""
        if not id_value:
            return True
        
        # Common patterns for generated IDs
        import re
        generated_patterns = [
            r'^[a-f0-9]{8,}$',           # Hex strings (like React IDs)
            r'^[a-z]+-[a-f0-9]{4,}$',    # prefix-hash pattern
            r'^\d+$',                     # Pure numbers
            r'^ember\d+$',                # Ember.js generated
            r'^react-',                   # React generated
            r'^ng-',                      # Angular generated
            r'^:r\d+:$',                  # React 18 useId
        ]
        
        for pattern in generated_patterns:
            if re.match(pattern, id_value, re.IGNORECASE):
                return True
        
        return False

    def _is_meaningful_href(self, href: str) -> bool:
        """Check if href is meaningful for selection."""
        if not href:
            return False
        
        # Skip non-meaningful hrefs
        skip_patterns = [
            "#",
            "javascript:",
            "mailto:",
            "tel:",
            "data:",
            "blob:",
        ]
        
        for pattern in skip_patterns:
            if href.startswith(pattern):
                return False
        
        # Skip very long hrefs (likely have query params that change)
        if len(href) > 100:
            return False
        
        return True

    def _get_specific_classes(self, classes: list) -> list:
        """Filter out generic utility classes, keep specific ones."""
        if not classes:
            return []
        
        # Generic/utility class patterns to skip
        generic_patterns = [
            # Layout
            "container", "wrapper", "row", "col", "flex", "grid", "block", "inline",
            # Spacing
            "mt-", "mb-", "ml-", "mr-", "mx-", "my-", "pt-", "pb-", "pl-", "pr-", "px-", "py-",
            "m-", "p-", "gap-",
            # Sizing
            "w-", "h-", "min-", "max-", "full", "auto", "screen",
            # Colors (utility)
            "text-", "bg-", "border-",
            # State
            "active", "disabled", "hidden", "visible", "show", "hide", "open", "closed",
            # Generic Bootstrap/Tailwind
            "btn", "form-control", "form-group", "input-group", "card", "modal",
            "nav", "navbar", "dropdown", "list-group",
            # Very short classes
        ]
        
        specific = []
        for cls in classes:
            cls_lower = cls.lower()
            
            # Skip very short classes
            if len(cls) < 3:
                continue
            
            # Skip if matches generic pattern
            is_generic = False
            for pattern in generic_patterns:
                if cls_lower == pattern or cls_lower.startswith(pattern):
                    is_generic = True
                    break
            
            if not is_generic:
                # Prefer classes with semantic naming (contains - or _)
                if "-" in cls or "_" in cls:
                    specific.insert(0, cls)  # Prioritize
                else:
                    specific.append(cls)
        
        return specific[:3]  # Return max 3 specific classes

    def _is_specific_selector(self, selector: str) -> bool:
        """Check if a CSS selector is specific enough to be reliable."""
        if not selector:
            return False
        
        # Just a tag name is not specific
        if selector in ["a", "button", "input", "select", "textarea", "div", "span", "li", "ul"]:
            return False
        
        # Has ID, attribute selector, or multiple parts = more specific
        specific_indicators = ["#", "[", " > ", " ", ":nth", ":has-text"]
        return any(indicator in selector for indicator in specific_indicators)

    def _fuzzy_find_element(
        self, 
        lookup: Dict[str, Dict], 
        page_id: str, 
        raw_key: str
    ) -> Optional[Dict]:
        """
        Try to find an element in the lookup, with fuzzy matching fallback.
        Priority: exact key > name+type match > tag+text match > tag only
        """
        canon_key = canonicalize_key(raw_key)
        full_key = f"{page_id}::{canon_key}"
        
        # 1. Exact match first
        if full_key in lookup:
            return lookup[full_key]
        
        # 2. Try matching without trailing pipes/spaces
        clean_key = canon_key.rstrip("| ")
        for key, info in lookup.items():
            if not key.startswith(f"{page_id}::"):
                continue
            stored_clean = key.split("::", 1)[1].rstrip("| ")
            if stored_clean == clean_key:
                return info
        
        # 3. Parse the key into parts: tag|text|id|name|type
        parts = canon_key.split("|")
        search_tag = parts[0].strip() if len(parts) > 0 else ""
        search_text = parts[1].strip() if len(parts) > 1 else ""
        search_id = parts[2].strip() if len(parts) > 2 else ""
        search_name = parts[3].strip() if len(parts) > 3 else ""
        search_type = parts[4].strip() if len(parts) > 4 else ""
        
        candidates = []
        
        for key, info in lookup.items():
            if not key.startswith(f"{page_id}::"):
                continue
            
            elem = info.get("element")
            if not elem:
                continue
            
            elem_tag = elem.tag or ""
            elem_text = (elem.text or "").strip()
            elem_id = elem.id or ""
            elem_name = elem.name or ""
            elem_type = elem.type or ""
            
            # Must match tag
            if elem_tag != search_tag:
                continue
            
            score = 0
            
            # 4. PRIORITY: Match by name (most reliable for form inputs)
            if search_name and elem_name:
                if elem_name == search_name:
                    score += 100  # Exact name match is very strong
                elif search_name in elem_name or elem_name in search_name:
                    score += 50
            
            # 5. Match by type
            if search_type and elem_type:
                if elem_type == search_type:
                    score += 80  # Exact type match
                elif search_type in elem_type:
                    score += 30
            
            # 6. Match by ID
            if search_id and elem_id:
                if elem_id == search_id:
                    score += 90
            
            # 7. Match by text
            if search_text and elem_text:
                if elem_text == search_text:
                    score += 70
                elif search_text in elem_text or elem_text in search_text:
                    score += 40
            
            # Only add if we have SOME match beyond just tag
            if score > 0:
                candidates.append((score, info))
            elif not search_name and not search_type and not search_id and not search_text:
                # No search criteria beyond tag - low score
                candidates.append((1, info))
        
        # Sort by score descending
        if candidates:
            candidates.sort(key=lambda x: -x[0])
            best_score, best_info = candidates[0]
            
            # Debug logging
            elem = best_info.get("element")
            if elem:
                print(f"  [fuzzy] Matched '{raw_key}' -> name={elem.name}, type={elem.type}, score={best_score}")
            
            return best_info
        
        print(f"  [fuzzy] No match found for '{raw_key}' in {page_id}")
        return None

    def _build_graph_preview(self, graph: SiteGraph) -> str:
        lines: List[str] = []

        for page_id, node in graph.pages.items():
            snap = node.snapshot
            lines.append(f"Page {page_id}: {snap.title} [{snap.url}]")
            # show elements with FULL unique key
            for e in snap.elements[:15]:  # Show more elements
                key = build_element_key(
                    e.tag, 
                    e.text, 
                    e.id,
                    name=e.name if e.tag in ["input", "select", "textarea"] else None,
                    input_type=e.type if e.tag in ["input", "select", "textarea"] else None
                )
                # Include name/type in preview for clarity
                extra = ""
                if e.tag == "input":
                    extra = f" name={e.name!r} type={e.type!r}"
                lines.append(
                    f"  - key={key}{extra} | css={e.css_selector!r}"
                )

        # add navigation edges
        lines.append("\nNavigation edges:")
        for edge in graph.edges:
            lines.append(
                f"  {edge.from_page_id} --({edge.element_key})-> {edge.to_page_id}"
            )

        return "\n".join(lines)

    def _ask_llm_for_plan(
        self, graph: SiteGraph, human_feedback: Optional[str]
    ) -> Dict:
      
        graph_preview = self._build_graph_preview(graph)
        feedback = human_feedback or "No feedback yet. Propose 3–8 good tests."

        system_msg = """
You are a senior QA engineer collaborating with a human tester.
You design HIGH-LEVEL logical test cases that may span MULTIPLE PAGES.

Rules:
- You DO NOT browse. You only know the site from the given pages and navigation edges.
- Focus on realistic user flows (e.g., sign in, basic navigation, search).
- Include both happy-path and negative/edge tests.
- Output STRICTLY valid JSON in the requested schema.
- Do NOT add meta commentary; only output JSON.
""".strip()

        user_msg = f"""
We have explored a small part of a website. Here is the graph:

{graph_preview}

The human feedback is:
\"\"\"feedback
{feedback}
\"\"\"

Using this information, design a set of MULTI-PAGE test cases.

Output JSON in this shape:

{{
  "test_cases": [
    {{
      "id": "string (e.g., TC_SIGNIN_VALID_01)",
      "name": "short descriptive name",
      "description": "what this scenario covers",
      "tags": ["functional", "happy_path", "..."],
      "steps": [
        {{
          "page_id": "page_0 or page_1 etc.",
          "action": "click|type|assert|navigate|other",
          "target_element_key": "one of the keys from the page's elements, or null",
          "details": "explanation, input value, or assertion text"
        }}
      ],
      "covered_elements": [
        {{
          "page_id": "page_x",
          "key": "element key from that page - MUST match exactly one of the keys listed above",
          "description": "short description of what this element does in the test"
        }}
      ]
    }}
  ],
  "coverage_summary": "short paragraph explaining which flows/pages are covered and notable gaps"
}}

Constraints:
- Create 3-8 test cases.
- When referencing an element, ALWAYS copy the key EXACTLY from the list above (including the trailing |).
- If a step is conceptual (no specific element), set target_element_key to null.
- For each covered_element, provide a short description of what it does in the test context.
"""

        raw = self.llm.chat(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=10000,
            temperature=0.2,
        )

        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()

        return json.loads(text)

    def build_plan(
        self, graph: SiteGraph, human_feedback: Optional[str] = None
    ) -> Dict:
        json_plan = self._ask_llm_for_plan(graph, human_feedback)
        element_lookup = self._build_element_lookup(graph)

        test_cases: List[TestCase] = []
        coverage: Dict[str, List[str]] = {}

        for tc_json in json_plan.get("test_cases", []):
            steps: List[TestStep] = []
            for st in tc_json.get("steps", []):
                page_id = st.get("page_id", "")
                raw_target = st.get("target_element_key")
                
                # Resolve the target element to get actual selectors
                resolved_target = None
                if raw_target and page_id:
                    elem_info = self._fuzzy_find_element(element_lookup, page_id, raw_target)
                    if elem_info:
                        elem = elem_info.get("element")
                        if elem:
                            # Build enriched target string with actual CSS selector
                            resolved_target = (
                                f"{elem_info['element_key']} "
                                f"name={elem.name!r} type={elem.type!r} | "
                                f"css='{elem.css_selector}'"
                            )
                        else:
                            resolved_target = raw_target
                    else:
                        resolved_target = raw_target
                
                steps.append(
                    TestStep(
                        action=st.get("action", ""),
                        page_id=page_id,
                        target=resolved_target,
                        details=st.get("details"),
                    )
                )

            # Build selectors from covered_elements
            covered_pairs = []
            selectors: List[SelectorInfo] = []
            seen_selectors = set()  # Prevent duplicates

            for ce in tc_json.get("covered_elements", []):
                pid = ce.get("page_id", "")
                raw_key = ce.get("key", "")
                llm_description = ce.get("description", "")

                if not pid or not raw_key:
                    continue

                # Find the element
                elem_info = self._fuzzy_find_element(element_lookup, pid, raw_key)
                
                if elem_info:
                    elem = elem_info.get("element")
                    actual_key = elem_info["element_key"]
                    
                    # Use actual key from lookup, not LLM's key
                    canon_key = actual_key
                    
                    # Track coverage with actual key
                    cov_key = f"{pid}::{canon_key}"
                    covered_pairs.append((pid, canon_key))
                    coverage.setdefault(cov_key, []).append(tc_json.get("id", ""))
                    
                    # Prevent duplicate selectors
                    selector_id = f"{pid}::{actual_key}"
                    if selector_id in seen_selectors:
                        continue
                    seen_selectors.add(selector_id)
                    
                    if elem:
                        selectors.append(
                            SelectorInfo(
                                element_key=actual_key,
                                page_id=pid,
                                css_selector=elem.css_selector,
                                xpath=elem.xpath,
                                description=llm_description or f"{elem.tag} element: {elem.name or elem.text or ''}",
                            )
                        )
                else:
                    # Element not found - use raw key
                    canon_key = canonicalize_key(raw_key)
                    cov_key = f"{pid}::{canon_key}"
                    covered_pairs.append((pid, canon_key))
                    coverage.setdefault(cov_key, []).append(tc_json.get("id", ""))
                    
                    selectors.append(
                        SelectorInfo(
                            element_key=canon_key,
                            page_id=pid,
                            css_selector=None,
                            xpath=None,
                            description=llm_description,
                        )
                    )

            tc = TestCase(
                id=tc_json.get("id", ""),
                name=tc_json.get("name", ""),
                description=tc_json.get("description", ""),
                tags=tc_json.get("tags", []),
                steps=steps,
                covered_element_keys=[f"{pid}::{key}" for pid, key in covered_pairs],
                selectors=selectors,
            )
            test_cases.append(tc)

        # Build pages info
        pages: Dict[str, Dict[str, str]] = {}
        for page_id, node in graph.pages.items():
            snap = node.snapshot
            pages[page_id] = {"url": snap.url, "title": snap.title}

        return {
            "test_cases": test_cases,
            "coverage": coverage,
            "pages": pages,
            "coverage_summary": json_plan.get("coverage_summary"),
        }