from __future__ import annotations
import json
from collections import Counter, deque
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from ..llm.ollama_client import LLMClient
from ..models.site_graph import SiteGraph
from ..models.test_case import TestCase, TestStep, SelectorInfo
from ..utils.keys import build_element_key, canonicalize_key
from ..metrics.metrics_recorder import get_metrics_tracker, PHASE_EXPLORATION

# ---------------------------------------------------------------------------
# Test-data constants — used by _get_input_value to fill missing input_values
# and to correct invalid values the LLM may produce.
# ---------------------------------------------------------------------------
_VALID_SUBJECTS = {
    "maths", "physics", "chemistry", "biology", "computer science",
    "commerce", "accounting", "economics", "arts", "social studies",
    "history", "civics", "hindi", "english", "sanskrit",
}
_SUBJECT_CORRECTIONS = {
    "mathematics": "Maths",
    "math": "Maths",
    "computer": "Computer Science",
    "cs": "Computer Science",
    "social": "Social Studies",
    "science": "Physics",
}
# Default values keyed by element id (lowercase) or name (lowercase).
# These are used when the LLM design step has no input_value at all.
_FIELD_DEFAULTS: Dict[str, str] = {
    # by id
    "firstname": "Alice",
    "lastname": "Johnson",
    "useremail": "alice.johnson@test.com",
    "usernumber": "1234567890",
    "dateofbirthinput": "10 Sep 1990",
    "currentaddress": "123 Main Street, Cityville",
    "subjectsautocomplete": "Maths",
    "state": "NCR",
    "city": "Delhi",
    # by name attribute
    "first_name": "Alice",
    "last_name": "Johnson",
    "email": "alice.johnson@test.com",
    "mobile": "1234567890",
    "phone": "1234567890",
    "address": "123 Main Street, Cityville",
    "subjects_autocomplete": "Maths",
}


class MultiPageTestDesignPipeline:
    """
    Given a SiteGraph (multiple pages + edges),
    propose HIGH-LEVEL multi-page test cases.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model=model_name)
        self._metrics = get_metrics_tracker()

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

    def _build_page_key_map(self, element_lookup: Dict[str, Dict]) -> Dict[str, Dict[str, str]]:
        """
        Build a per-page map of canonical_key -> actual_key.
        """
        page_keys: Dict[str, Dict[str, str]] = {}
        for full_key, info in element_lookup.items():
            if "::" not in full_key:
                continue
            page_id, actual_key = full_key.split("::", 1)
            canon_key = canonicalize_key(actual_key)
            page_keys.setdefault(page_id, {})[canon_key] = actual_key
        return page_keys

    def _build_edge_map(self, graph: SiteGraph) -> Dict[str, Dict[str, Dict[str, str]]]:
        """
        Build map: from_page_id -> canonical_element_key -> {dest, key}.
        """
        edge_map: Dict[str, Dict[str, Dict[str, str]]] = {}
        for edge in graph.edges:
            canon_key = canonicalize_key(edge.element_key)
            edge_map.setdefault(edge.from_page_id, {})[canon_key] = {
                "dest": edge.to_page_id,
                "key": edge.element_key,
            }
        return edge_map

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ""
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if base.endswith("/") and base != f"{parsed.scheme}://{parsed.netloc}/":
            base = base.rstrip("/")
        return base

    def _build_url_page_map(self, graph: SiteGraph) -> Dict[str, str]:
        url_map: Dict[str, str] = {}
        for page_id, node in graph.pages.items():
            normalized = self._normalize_url(node.snapshot.url)
            if normalized:
                url_map[normalized] = page_id
        return url_map

    def _build_inferred_edge_map(
        self,
        graph: SiteGraph,
        page_keys: Dict[str, Dict[str, str]],
    ) -> Dict[str, Dict[str, Dict[str, str]]]:
        """
        Infer navigation edges based on link hrefs pointing to known pages.
        """
        inferred: Dict[str, Dict[str, Dict[str, str]]] = {}
        url_map = self._build_url_page_map(graph)

        for page_id, node in graph.pages.items():
            base_url = node.snapshot.url
            for e in node.snapshot.elements:
                if e.tag != "a":
                    continue
                href = (e.attributes or {}).get("href") or ""
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:", "blob:")):
                    continue
                abs_url = urljoin(base_url, href)
                dest_page = url_map.get(self._normalize_url(abs_url))
                if not dest_page or dest_page == page_id:
                    continue

                key = build_element_key(e.tag, e.text, e.id)
                canon_key = canonicalize_key(key)
                actual_key = page_keys.get(page_id, {}).get(canon_key, key)

                inferred.setdefault(page_id, {}).setdefault(
                    canon_key,
                    {"dest": dest_page, "key": actual_key},
                )

        return inferred

    def _merge_edge_maps(
        self,
        primary: Dict[str, Dict[str, Dict[str, str]]],
        secondary: Dict[str, Dict[str, Dict[str, str]]],
    ) -> Dict[str, Dict[str, Dict[str, str]]]:
        merged = {pid: edges.copy() for pid, edges in primary.items()}
        for page_id, edges in secondary.items():
            for canon_key, info in edges.items():
                merged.setdefault(page_id, {}).setdefault(canon_key, info)
        return merged

    def _build_key_frequency(self, page_keys: Dict[str, Dict[str, str]]) -> Counter:
        counts: Counter = Counter()
        for keys in page_keys.values():
            for actual_key in keys.values():
                canon = canonicalize_key(actual_key)
                if canon:
                    counts[canon] += 1
        return counts

    def _score_page_marker(self, element, is_unique: bool) -> int:
        score = 0
        if is_unique:
            score += 100
        if element.tag in ["input", "select", "textarea"]:
            score += 40
        elif element.tag == "button":
            score += 30
        elif element.tag == "a":
            score += 15

        text = (element.text or "").strip()
        if text:
            score += min(len(text), 30)
            if text.lower() in {
                "home",
                "products",
                "cart",
                "signup / login",
                "test cases",
                "api testing",
                "video tutorials",
                "contact us",
            }:
                score -= 25

        if element.id:
            score += 10
        if element.name:
            score += 5
        if element.aria_label:
            score += 5
        return score

    def _build_page_markers(
        self,
        graph: SiteGraph,
        element_lookup: Dict[str, Dict],
        page_keys: Dict[str, Dict[str, str]],
        key_frequency: Counter,
    ) -> Dict[str, str]:
        markers: Dict[str, str] = {}
        for page_id in graph.pages.keys():
            candidates = []
            for actual_key in page_keys.get(page_id, {}).values():
                canon = canonicalize_key(actual_key)
                elem_info = element_lookup.get(f"{page_id}::{actual_key}")
                if not elem_info:
                    continue
                elem = elem_info.get("element")
                if not elem:
                    continue
                is_unique = key_frequency.get(canon, 0) == 1
                score = self._score_page_marker(elem, is_unique)
                candidates.append((score, actual_key))
            if not candidates:
                continue
            candidates.sort(key=lambda x: -x[0])
            markers[page_id] = candidates[0][1]
        return markers

    def _find_navigation_path(
        self,
        start_page: str,
        target_page: str,
        edge_map: Dict[str, Dict[str, Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        if not start_page or not target_page:
            return []
        if start_page == target_page:
            return []

        queue = deque([(start_page, [])])
        visited = {start_page}

        while queue:
            page_id, path = queue.popleft()
            for info in edge_map.get(page_id, {}).values():
                dest = info.get("dest")
                key = info.get("key")
                if not dest or not key:
                    continue
                step = {"from": page_id, "key": key, "dest": dest}
                if dest == target_page:
                    return path + [step]
                if dest not in visited:
                    visited.add(dest)
                    queue.append((dest, path + [step]))

        return []

    def _is_weak_assert(
        self,
        page_id: str,
        element_key: str,
        key_frequency: Counter,
        element_lookup: Dict[str, Dict],
    ) -> bool:
        canon = canonicalize_key(element_key)
        if key_frequency.get(canon, 0) > 1:
            return True
        info = element_lookup.get(f"{page_id}::{element_key}")
        if not info:
            return True
        elem = info.get("element")
        if not elem:
            return True
        text = (elem.text or "").strip().lower()
        if text in {
            "home",
            "products",
            "cart",
            "signup / login",
            "test cases",
            "api testing",
            "video tutorials",
            "contact us",
        }:
            return True
        return False

    def _is_submit_like(self, element) -> bool:
        if not element:
            return False
        if element.tag == "button":
            return True
        if element.tag == "input" and element.type in ["submit", "button"]:
            return True
        return False

    def _find_start_page_id(self, graph: SiteGraph, start_url: Optional[str]) -> Optional[str]:
        if not start_url:
            return None
        for page_id, node in graph.pages.items():
            if node.snapshot.url == start_url:
                return page_id
        return None

    def _resolve_key(
        self,
        page_id: str,
        raw_key: Optional[str],
        page_keys: Dict[str, Dict[str, str]],
    ) -> Optional[str]:
        if not raw_key or not page_id:
            return None
        canon_key = canonicalize_key(raw_key)
        return page_keys.get(page_id, {}).get(canon_key)

    def _page_assertion_steps(
        self,
        graph: SiteGraph,
        page_id: str,
        page_markers: Dict[str, str],
    ) -> List[Dict]:
        if page_id not in graph.pages:
            return []
        marker_key = page_markers.get(page_id)
        if not marker_key:
            return []
        url = graph.pages[page_id].snapshot.url
        return [
            {
                "page_id": page_id,
                "action": "assert",
                "target_element_key": marker_key,
                "details": f"Confirm page is loaded: {url}",
            }
        ]

    def _is_non_success_submit_case(self, tc_text: str) -> bool:
        """Return True for negative / edge / ambiguous submit scenarios."""
        negative_markers = (
            "invalid", "empty", "missing", "boundary", "edge", "special",
            "error", "reject", "rejected", "validation", "unsupported",
            "too long", "too short", "malformed", "bad input",
        )
        success_markers = (
            "happy path", "happy_path", "valid data", "successful",
            "successfully", "success case",
        )
        return any(marker in tc_text for marker in negative_markers) and not any(
            marker in tc_text for marker in success_markers
        )

    def _is_modal_or_icon_target(
        self,
        page_id: str,
        element_key: Optional[str],
        element_lookup: Dict[str, Dict],
    ) -> bool:
        """Detect modal-only elements or icon-button targets that should not be used as success evidence."""
        if not element_key:
            return False

        raw = canonicalize_key(element_key).lower()
        if any(token in raw for token in ("resultsmodal", "closelargemodal", "button|event|", "button|close|")):
            return True

        info = element_lookup.get(f"{page_id}::{element_key}")
        elem = info.get("element") if info else None
        if not elem:
            return False

        elem_id = (elem.id or "").lower()
        elem_text = (elem.text or "").strip().lower()
        return elem_id in {"resultsmodal", "closelargemodal"} or elem_text in {"event", "close"}

    def _build_non_success_post_submit_assert(
        self,
        page_id: str,
        tc_text: str,
        page_markers: Dict[str, str],
        element_lookup: Dict[str, Dict],
    ) -> Optional[Dict]:
        """Build a deterministic follow-up assert for negative / edge submit attempts."""
        target_key = page_markers.get(page_id)
        details = (
            "Verify the form remains on the page after the submit attempt. "
            "Do NOT assume the success modal appears for this negative or edge scenario."
        )
        expected_result = "Practice form remains visible and usable after the submit attempt"

        if "special" in tc_text:
            for full_key, info in element_lookup.items():
                if not full_key.startswith(f"{page_id}::"):
                    continue
                elem = info.get("element")
                if elem and elem.id == "firstName":
                    target_key = info.get("element_key") or target_key
                    break
            details = "Verify the first name field remains visible after the submit attempt; special-character input must not crash the page."
            expected_result = "First name field remains visible and the page stays usable after the submit attempt"
        elif "email" in tc_text:
            for full_key, info in element_lookup.items():
                if not full_key.startswith(f"{page_id}::"):
                    continue
                elem = info.get("element")
                if elem and elem.id == "userEmail":
                    target_key = info.get("element_key") or target_key
                    break
            details = "Verify the email field remains visible after the submit attempt; do NOT assume success modal for invalid email."
            expected_result = "Email field remains visible and the form stays on the same page after the submit attempt"
        elif "mobile" in tc_text or "phone" in tc_text:
            for full_key, info in element_lookup.items():
                if not full_key.startswith(f"{page_id}::"):
                    continue
                elem = info.get("element")
                if elem and elem.id == "userNumber":
                    target_key = info.get("element_key") or target_key
                    break
            details = "Verify the mobile field remains visible after the submit attempt; do NOT assume success modal for boundary input."
            expected_result = "Mobile field remains visible and the form stays on the same page after the submit attempt"

        if not target_key:
            return None

        return {
            "page_id": page_id,
            "action": "assert",
            "target_element_key": target_key,
            "details": details,
            "expected_result": expected_result,
        }

    def _validate_and_fix_plan(self, json_plan: Dict, graph: SiteGraph) -> Dict:
        """
        Enforce page coherence and element validity against the graph.
        Ensures all steps reference valid elements on the correct page.
        """
        element_lookup = self._build_element_lookup(graph)
        page_keys = self._build_page_key_map(element_lookup)
        explicit_edges = self._build_edge_map(graph)
        inferred_edges = self._build_inferred_edge_map(graph, page_keys)
        edge_map = self._merge_edge_maps(explicit_edges, inferred_edges)
        key_frequency = self._build_key_frequency(page_keys)
        page_markers = self._build_page_markers(graph, element_lookup, page_keys, key_frequency)
        
        # Build email inputs map for validation
        email_inputs: Dict[str, List[str]] = {}
        for info in element_lookup.values():
            elem = info.get("element")
            page_id = info.get("page_id")
            if not elem or not page_id:
                continue
            if elem.tag == "input" and elem.type == "email":
                email_inputs.setdefault(page_id, []).append(info.get("element_key"))
        
        start_page_id = self._find_start_page_id(graph, json_plan.get("start_url"))
        
        # If no start_url, default to first page
        if not start_page_id and graph.pages:
            start_page_id = list(graph.pages.keys())[0]
            if not json_plan.get("start_url"):
                json_plan["start_url"] = graph.pages[start_page_id].snapshot.url

        for tc_json in json_plan.get("test_cases", []):
            current_page = start_page_id
            new_steps: List[Dict] = []
            covered_map: Dict[str, Dict] = {}
            typed_email_pages = set()
            added_non_success_post_submit_assert = False
            step_number = 0

            tc_text = f"{tc_json.get('name', '')} {tc_json.get('description', '')}".lower()
            needs_invalid_email = "invalid" in tc_text and "email" in tc_text and "empty" not in tc_text
            non_success_submit_case = self._is_non_success_submit_case(tc_text)

            def add_step(step: Dict) -> None:
                nonlocal step_number
                # Prevent duplicate consecutive assertions on same element
                if (
                    step.get("action") == "assert"
                    and new_steps
                    and new_steps[-1].get("action") == "assert"
                    and new_steps[-1].get("target_element_key") == step.get("target_element_key")
                ):
                    return
                step_number += 1
                step["step_number"] = step_number
                
                # Add URL context for the page
                if step.get("page_id") and step["page_id"] in graph.pages:
                    step["page_url"] = graph.pages[step["page_id"]].snapshot.url
                
                new_steps.append(step)

            def add_page_assert(page_id: str) -> None:
                for step in self._page_assertion_steps(graph, page_id, page_markers):
                    step["expected_result"] = f"Page '{graph.pages[page_id].snapshot.title}' is loaded and visible"
                    add_step(step)

            # Start with assertion on the initial page
            if current_page:
                add_page_assert(current_page)

            for st in tc_json.get("steps", []):
                action = st.get("action", "")
                step_page_id = st.get("page_id") or current_page
                raw_target = st.get("target_element_key")
                details = st.get("details")
                input_value = st.get("input_value")
                expected_result = st.get("expected_result")

                # CRITICAL: Validate page_id exists
                if step_page_id not in graph.pages:
                    # Try to use current page instead
                    step_page_id = current_page
                    if not step_page_id or step_page_id not in graph.pages:
                        print(f"  [validation] Skipping step with invalid page: {st}")
                        continue

                # Handle navigate action (going to a URL directly)
                if action == "navigate":
                    if step_page_id and step_page_id in graph.pages:
                        current_page = step_page_id
                        add_step({
                            "page_id": step_page_id,
                            "action": action,
                            "target_element_key": None,
                            "details": details or f"Navigate to {graph.pages[step_page_id].snapshot.url}",
                            "expected_result": expected_result or f"Browser navigates to {graph.pages[step_page_id].snapshot.title}",
                        })
                        add_page_assert(step_page_id)
                    continue

                # CRITICAL: If step targets a different page, we need navigation
                if current_page and step_page_id and step_page_id != current_page:
                    nav_path = self._find_navigation_path(current_page, step_page_id, edge_map)
                    if not nav_path:
                        print(f"  [validation] No navigation path from {current_page} to {step_page_id}, skipping step")
                        continue
                    
                    # Add navigation steps
                    for nav_step in nav_path:
                        add_step({
                            "page_id": nav_step["from"],
                            "action": "click",
                            "target_element_key": nav_step["key"],
                            "details": f"Click to navigate to {nav_step['dest']}",
                            "expected_result": f"Browser navigates to {graph.pages[nav_step['dest']].snapshot.title if nav_step['dest'] in graph.pages else nav_step['dest']}",
                        })
                        current_page = nav_step["dest"]
                        add_page_assert(current_page)

                # Now we should be on the correct page
                # CRITICAL: Verify target element exists on CURRENT page
                resolved_key = None
                if raw_target:
                    # First try exact resolution on current page (not step_page_id which might differ)
                    resolved_key = self._resolve_key(current_page, raw_target, page_keys)
                    if not resolved_key:
                        elem_info = self._fuzzy_find_element(element_lookup, current_page, raw_target)
                        if elem_info:
                            resolved_key = elem_info.get("element_key")
                        else:
                            print(f"  [validation] Element '{raw_target}' not found on {current_page}, skipping")
                            continue

                # Handle assertions
                if action == "assert":
                    if not resolved_key or self._is_weak_assert(current_page, resolved_key, key_frequency, element_lookup):
                        resolved_key = page_markers.get(current_page) or resolved_key
                    if not resolved_key:
                        continue

                # Skip if we needed a target but couldn't resolve it
                if raw_target and not resolved_key:
                    continue

                # For negative / edge submit tests, never use modal/icon-only elements
                # as success evidence or as close actions.
                if (
                    action in {"assert", "click"}
                    and non_success_submit_case
                    and self._is_modal_or_icon_target(current_page, resolved_key, element_lookup)
                ):
                    continue

                # Track email typing
                if action == "type" and resolved_key:
                    if resolved_key in (email_inputs.get(current_page) or []):
                        typed_email_pages.add(current_page)

                # For invalid email tests, inject email typing before submit
                if action == "click" and resolved_key and needs_invalid_email:
                    if current_page in email_inputs and current_page not in typed_email_pages:
                        info = element_lookup.get(f"{current_page}::{resolved_key}")
                        if info and self._is_submit_like(info.get("element")):
                            email_key = email_inputs[current_page][0]
                            add_step({
                                "page_id": current_page,
                                "action": "type",
                                "target_element_key": email_key,
                                "input_value": "invalid-email",
                                "details": "Enter invalid email value",
                                "expected_result": "Invalid email is entered in the field",
                            })
                            typed_email_pages.add(current_page)

                # Build the validated step
                validated_step = {
                    "page_id": current_page,  # Use current_page, not step_page_id
                    "action": action,
                    "target_element_key": resolved_key,
                    "details": details,
                    "expected_result": expected_result or self._infer_expected_result(action, resolved_key, current_page, graph),
                }
                
                if input_value:
                    validated_step["input_value"] = input_value

                # For "type" steps, always ensure a concrete input_value is set.
                # _get_input_value validates provided values (e.g. corrects wrong subject
                # names), injects sensible defaults when input_value is missing, and
                # emits "NeedToAsk: ..." markers when no default can be inferred.
                if action == "type":
                    enriched_val = self._get_input_value(
                        validated_step.get("input_value"),
                        resolved_key,
                        current_page,
                        element_lookup,
                    )
                    if enriched_val is not None:
                        validated_step["input_value"] = enriched_val

                add_step(validated_step)

                # For non-success submission scenarios, inject a deterministic follow-up
                # assert that keeps the test meaningful without assuming the success modal.
                info = element_lookup.get(f"{current_page}::{resolved_key}") if resolved_key else None
                if (
                    action == "click"
                    and info
                    and self._is_submit_like(info.get("element"))
                    and non_success_submit_case
                    and not added_non_success_post_submit_assert
                ):
                    follow_up_assert = self._build_non_success_post_submit_assert(
                        current_page,
                        tc_text,
                        page_markers,
                        element_lookup,
                    )
                    if follow_up_assert:
                        add_step(follow_up_assert)
                        added_non_success_post_submit_assert = True

                # Update current page if clicking a navigation element
                if action == "click" and resolved_key and current_page:
                    edge_info = edge_map.get(current_page, {}).get(canonicalize_key(resolved_key))
                    if edge_info:
                        current_page = edge_info.get("dest")
                        if current_page:
                            add_page_assert(current_page)

            # End with a final assertion if not already present
            if current_page and (not new_steps or new_steps[-1].get("action") != "assert"):
                add_page_assert(current_page)

            tc_json["steps"] = new_steps
            tc_json["final_page"] = current_page

            # Validate and fix covered_elements
            for ce in tc_json.get("covered_elements", []):
                pid = ce.get("page_id")
                raw_key = ce.get("key")
                if pid not in graph.pages:
                    continue
                resolved = self._resolve_key(pid, raw_key, page_keys)
                if not resolved:
                    elem_info = self._fuzzy_find_element(element_lookup, pid, raw_key)
                    if elem_info:
                        resolved = elem_info.get("element_key")
                if not resolved:
                    continue
                ce["key"] = resolved
                covered_map[f"{pid}::{resolved}"] = ce

            # Add elements from steps to covered_elements
            for step in new_steps:
                step_key = step.get("target_element_key")
                step_page = step.get("page_id")
                if not step_key or not step_page:
                    continue
                map_key = f"{step_page}::{step_key}"
                if map_key in covered_map:
                    continue
                covered_map[map_key] = {
                    "page_id": step_page,
                    "key": step_key,
                    "interaction_type": step.get("action"),
                    "description": f"Used for {step.get('action')} step",
                }

            tc_json["covered_elements"] = list(covered_map.values())

        return json_plan

    def _infer_expected_result(self, action: str, element_key: Optional[str], page_id: str, graph: SiteGraph) -> str:
        """Infer a reasonable expected result based on action type."""
        if action == "click":
            return "Element is clicked successfully"
        elif action == "type":
            return "Text is entered into the field"
        elif action == "assert":
            return "Element is visible and matches expected state"
        elif action == "clear":
            return "Field is cleared"
        elif action == "select":
            return "Option is selected from dropdown"
        elif action == "hover":
            return "Mouse hovers over element"
        elif action == "wait":
            return "Wait completed"
        else:
            return "Action completed successfully"

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

    @staticmethod
    def _get_input_value(
        provided_value: Optional[str],
        element_key: Optional[str],
        page_id: str,
        element_lookup: Dict[str, Dict],
    ) -> Optional[str]:
        """
        Return the best concrete input_value for a 'type' step.

        Priority:
          1. Provided value — validated / corrected where needed (e.g. wrong subject name)
          2. Field-specific default derived from element id / name
          3. Type-based fallback
          4. NeedToAsk marker (signals that a human must supply the value)

        NeedToAsk values pass through unchanged so the code generator can
        emit placeholder constants in the generated test.
        """
        # Resolve element metadata for context
        elem_info = element_lookup.get(f"{page_id}::{element_key}") if element_key else None
        elem = elem_info.get("element") if elem_info else None

        elem_id = (elem.id or "").lower().replace("-", "").replace("_", "") if elem else ""
        elem_name = (elem.name or "").lower().replace("-", "").replace("_", "") if elem else ""
        elem_id_raw = (elem.id or "").lower() if elem else ""
        elem_name_raw = (elem.name or "").lower() if elem else ""
        elem_type = (elem.type or "").lower() if elem else ""

        # ── 1. Validate / correct a provided value ──────────────────────────
        if provided_value and str(provided_value).strip():
            val = str(provided_value).strip()

            # NeedToAsk markers pass through unchanged
            if val.lower().startswith("needtoask"):
                return val

            # Correct invalid subject names
            is_subjects_field = "subjects" in elem_id or "subjects" in elem_name
            if is_subjects_field:
                val_lower = val.lower()
                if val_lower not in _VALID_SUBJECTS:
                    corrected = _SUBJECT_CORRECTIONS.get(val_lower)
                    if corrected:
                        return corrected
                    # Partial-prefix match
                    for sub in sorted(_VALID_SUBJECTS):
                        if sub.startswith(val_lower[:3]):
                            # Capitalise properly
                            return " ".join(w.capitalize() for w in sub.split())
                    return "Maths"  # safe fallback
            return val  # value looks fine

        # ── 2. Inject a field-specific default ──────────────────────────────
        for lookup_key in (elem_id, elem_name, elem_id_raw, elem_name_raw):
            if lookup_key and lookup_key in _FIELD_DEFAULTS:
                return _FIELD_DEFAULTS[lookup_key]

        # ── 3. Type-based fallback ───────────────────────────────────────────
        type_fallbacks = {
            "email": "test.user@example.com",
            "tel": "1234567890",
            "number": "42",
            "date": "10 Sep 1990",
            "text": "Test Value",
        }
        if elem_type in type_fallbacks:
            return type_fallbacks[elem_type]

        # ── 4. NeedToAsk — human must supply the value ───────────────────────
        field_desc = (
            elem.name or elem.id or elem.placeholder
            if elem else element_key or "this field"
        )
        return f"NeedToAsk: Please provide a valid value for '{field_desc}'"

    def _build_page_elements_summary(self, graph: SiteGraph) -> str:
        """
        Build a detailed, categorized summary of elements per page.
        This helps the LLM understand what's available on each page.
        """
        lines: List[str] = []
        
        for page_id, node in graph.pages.items():
            snap = node.snapshot
            lines.append(f"\n### {page_id}: {snap.title}")
            lines.append(f"URL: {snap.url}")
            
            # Categorize elements (nav_links separated so they appear last)
            _ICON_WORDS = {
                "event", "close", "search", "menu", "more_vert", "more_horiz",
                "expand_more", "expand_less", "chevron_right", "chevron_left",
                "arrow_drop_down", "arrow_forward", "arrow_back", "edit",
                "delete", "add", "remove", "check", "clear", "done",
                "keyboard_arrow_down", "keyboard_arrow_up",
            }

            forms = []
            submit_inputs = []   # input[type=submit] or input[type=button]
            inputs = []
            buttons = []         # real action buttons (not icon-only)
            icon_buttons = []    # small icon-only buttons — should NOT be used for form submit
            links = []           # main content links
            nav_links = []       # navbar / sidebar links
            headings = []
            other_interactive = []

            for e in snap.elements:
                key = build_element_key(
                    e.tag,
                    e.text,
                    e.id,
                    name=e.name if e.tag in ["input", "select", "textarea"] else None,
                    input_type=e.type if e.tag in ["input", "select", "textarea"] else None,
                )

                elem_desc = {
                    "key": key,
                    "text": (e.text or "")[:50],
                    "id": e.id,
                    "name": e.name,
                    "type": e.type,
                    "css": e.css_selector,
                }

                if e.tag == "form":
                    forms.append(elem_desc)
                elif e.tag == "input":
                    if e.type in ("submit", "button", "reset"):
                        submit_inputs.append(elem_desc)
                    else:
                        inputs.append(elem_desc)
                elif e.tag == "button":
                    raw_text = (e.text or "").strip().lower()
                    # A button whose entire visible text is a single Material-icon word
                    # is an icon button (e.g. the gijgo calendar icon renders as "event").
                    if raw_text in _ICON_WORDS or (len(raw_text) <= 20 and raw_text in _ICON_WORDS):
                        icon_buttons.append(elem_desc)
                    else:
                        buttons.append(elem_desc)
                elif e.tag == "a":
                    if e.is_nav_or_sidebar():
                        nav_links.append(elem_desc)
                    else:
                        links.append(elem_desc)
                elif e.tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                    headings.append(elem_desc)
                elif e.tag in ["select", "textarea"]:
                    other_interactive.append(elem_desc)

            # Output categorized elements with clear labels.
            # Submit inputs come FIRST so the LLM cannot miss the real submit button.
            if submit_inputs:
                lines.append("\n**FORM SUBMIT BUTTON** ← USE THIS to submit the form:")
                for s in submit_inputs:
                    lines.append(f"  - KEY: \"{s['key']}\"")
                    lines.append(f"    type={s['type']!r} name={s['name']!r} id={s['id']!r} css={s['css']!r}")

            if inputs:
                lines.append("\n**INPUT FIELDS** (for typing data):")
                for inp in inputs[:10]:
                    lines.append(f"  - KEY: \"{inp['key']}\"")
                    lines.append(f"    name={inp['name']!r} type={inp['type']!r} id={inp['id']!r}")

            if buttons:
                lines.append("\n**BUTTONS** (for clicking / triggering actions):")
                for btn in buttons[:8]:
                    lines.append(f"  - KEY: \"{btn['key']}\"")
                    lines.append(f"    text={btn['text']!r} id={btn['id']!r}")

            if icon_buttons:
                lines.append(
                    "\n**ICON-ONLY BUTTONS** ⚠️  DO NOT use these for form submission — "
                    "they are UI widget icons (calendar picker, close, etc.):"
                )
                for btn in icon_buttons:
                    lines.append(f"  - KEY: \"{btn['key']}\"  text={btn['text']!r}  (icon button)")

            if links:
                lines.append("\n**LINKS – MAIN CONTENT** (for navigation):")
                for lnk in links[:10]:
                    lines.append(f"  - KEY: \"{lnk['key']}\"")
                    lines.append(f"    text={lnk['text']!r}")

            if headings:
                lines.append("\n**HEADINGS** (for page identification/assertions):")
                for hdg in headings[:5]:
                    lines.append(f"  - KEY: \"{hdg['key']}\"")
                    lines.append(f"    text={hdg['text']!r}")

            if other_interactive:
                lines.append("\n**OTHER FORM ELEMENTS**:")
                for elem in other_interactive[:5]:
                    lines.append(f"  - KEY: \"{elem['key']}\"")
                    lines.append(f"    name={elem['name']!r} type={elem['type']!r}")

            if nav_links:
                lines.append("\n**NAVBAR / SIDEBAR LINKS** (LOWEST PRIORITY – test only if main content is fully covered):")
                for lnk in nav_links[:10]:
                    lines.append(f"  - KEY: \"{lnk['key']}\"")
                    lines.append(f"    text={lnk['text']!r}")
        
        return "\n".join(lines)

    def _build_navigation_guide(self, graph: SiteGraph) -> str:
        """
        Build a clear navigation guide showing how pages connect.
        This helps the LLM understand valid navigation paths.
        """
        lines: List[str] = []
        
        # Build adjacency info
        nav_from: Dict[str, List[Dict]] = {}
        for edge in graph.edges:
            nav_from.setdefault(edge.from_page_id, []).append({
                "dest": edge.to_page_id,
                "element_key": edge.element_key,
                "dest_url": graph.pages[edge.to_page_id].snapshot.url if edge.to_page_id in graph.pages else "unknown"
            })
        
        lines.append("From each page, you can navigate to:")
        
        for page_id, node in graph.pages.items():
            edges = nav_from.get(page_id, [])
            lines.append(f"\n{page_id} ({node.snapshot.title}):")
            if edges:
                for edge in edges:
                    lines.append(f"  → Click \"{edge['element_key']}\" to go to {edge['dest']}")
            else:
                lines.append(f"  (No outgoing navigation edges discovered)")
        
        # Add a note about page tracking
        lines.append("\n**IMPORTANT**: After clicking a navigation element, your current_page changes to the destination.")
        lines.append("You can then ONLY interact with elements on the new page.")
        
        return "\n".join(lines)

    def _build_graph_preview(self, graph: SiteGraph) -> str:
        lines: List[str] = []

        for page_id, node in graph.pages.items():
            snap = node.snapshot
            lines.append(f"Page {page_id}: {snap.title} [{snap.url}]")
            # Show main-content elements first, nav/sidebar elements last.
            sorted_elems = sorted(snap.elements, key=lambda e: 1 if e.is_nav_or_sidebar() else 0)
            for e in sorted_elems[:15]:  # Show more elements
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
                nav_note = " [nav/sidebar]" if e.is_nav_or_sidebar() else ""
                lines.append(
                    f"  - key={key}{extra} | css={e.css_selector!r}{nav_note}"
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
        feedback = human_feedback or "No feedback yet. Propose 3-8 good tests."

        system_msg = """
You are a senior QA automation engineer designing executable test cases.
You create PRECISE, PAGE-COHERENT test cases that can be directly converted to Playwright/Selenium code.

CRITICAL RULES:
1. PAGE COHERENCE: Every step MUST specify which page it executes on. You can ONLY interact with elements on your CURRENT page.
2. NAVIGATION: To change pages, you MUST click a navigation element (link/button) that has an edge to the target page. After clicking, update your current page.
3. ASSERTIONS: ONLY assert on elements that exist on the CURRENT page. Never assert on elements from a previous page.
4. ELEMENT KEYS: Copy element keys EXACTLY as shown (including trailing |). These are used for selector lookup.
5. STEP ORDER: Steps must be executable in sequence. Each step's page_id must match where you currently are.
6. EXPLICIT NAVIGATION: Include explicit "navigate" steps when going to a URL, or "click" steps when using links.
7. PRECONDITIONS: Each test should start from the start_url and explicitly navigate to where it needs to be.
8. EXPECTED RESULTS: Each assertion must have a clear expected outcome in the details field.

ELEMENT PRIORITY (IMPORTANT):
- FIRST focus test cases on INPUT FIELDS, BUTTONS, and MAIN CONTENT LINKS — these are the primary test targets.
- "NAVBAR / SIDEBAR LINKS" sections in the element summary are LOWEST PRIORITY.
  Only design tests for them after all main-content scenarios are covered, or if navigation verification is explicitly requested.
- Elements tagged [nav/sidebar] in the graph preview are navigation chrome, not core functionality.

FORM SUBMIT BUTTON RULES (CRITICAL):
- The real submit button is listed under "FORM SUBMIT BUTTON" in the element summary.
  It is an `input[type="submit"]` or `button[type="submit"]`.
  Use ONLY this element to submit a form.
- "ICON-ONLY BUTTONS" (text: "event", "close", "search", etc.) are widget icons — NOT submit actions.
  NEVER use an icon-only button as a form submission step.
- ONLY for clear happy-path / valid-data submissions: assert the results modal is visible
    and add a close step using the real modal close button.
- For negative, boundary, validation, or ambiguous-acceptance tests (special chars, invalid email,
    empty fields, unsupported input, etc.), DO NOT assume the success modal will appear.
    Instead design a deterministic oracle such as:
    - same page remains visible,
    - field value remains present,
    - form stays usable,
    - validation blocks submission.
- Never use an icon-only button (e.g. text "event") as evidence that the modal is open.

CUSTOM WIDGET RULES:
- State/City fields use a CUSTOM DROPDOWN widget (.custom-dropdown-control / .custom-dropdown-option),
  NOT a native select. Design steps as: click the control div, then click the desired option div.
- The Subjects field is an AUTOCOMPLETE: type partial text, then click a suggestion item.
  Valid subjects: Maths, Physics, Chemistry, Biology, Computer Science, Commerce, Accounting,
  Economics, Arts, Social Studies, History, Civics, Hindi, English, Sanskrit.

TEST DATA SPECIFICATION (CRITICAL):
Every "type" action step MUST have "input_value" set to a concrete, exact value. Rules:
1. Use realistic fictional data — NEVER leave "input_value" null or vague for a "type" step.
     firstName → "Alice"        lastName → "Johnson"
     email     → "alice.johnson@test.com"      mobile   → "1234567890"  (exactly 10 digits)
     address   → "123 Main Street, Cityville"  dob      → "10 Sep 1990"
2. For SUBJECTS AUTOCOMPLETE, "input_value" MUST be one of these EXACT strings (full name):
     "Maths", "Physics", "Chemistry", "Biology", "Computer Science", "Commerce",
     "Accounting", "Economics", "Arts", "Social Studies", "History", "Civics",
     "Hindi", "English", "Sanskrit"
   NEVER use "Mathematics", "Math", "Computer", or any other variation.
3. For STATE and CITY dropdowns, "input_value" must be the exact visible option text.
     Valid states: "NCR", "Uttar Pradesh", "Haryana", "Rajasthan"
     Cities for NCR: "Delhi", "Gurgaon", "Noida"
4. If the correct value is UNKNOWN (real password, account token, API key), set:
     "input_value": "NeedToAsk: <one sentence describing what value is needed>"
   Example: "NeedToAsk: Valid login password for the qa-practice.com test account"
5. For NEGATIVE tests: invalid email = "invalid-email-format",
     too-long mobile = "12345678901" (11 digits), special chars = "Élise!@#".

TEST ORACLE RULES (CRITICAL):
- Every test MUST have a deterministic oracle.
- NEVER write conditional outcomes such as "if accepted..." or "manual check needed".
- If behavior is uncertain, choose an observable assertion that is always valid, such as
    field visibility, field value preservation, same-page behavior, or blocked submission.

OUTPUT FORMAT:
- Output STRICTLY valid JSON in the requested schema.
- Do NOT add meta commentary; only output JSON.
""".strip()

        # Build page-to-elements mapping for clarity
        page_elements_summary = self._build_page_elements_summary(graph)
        navigation_guide = self._build_navigation_guide(graph)

        user_msg = f"""
=== WEBSITE STRUCTURE ===
{graph_preview}

=== PAGE ELEMENTS SUMMARY ===
{page_elements_summary}

=== NAVIGATION PATHS ===
{navigation_guide}

=== HUMAN FEEDBACK ===
{feedback}

=== YOUR TASK ===
Design EXECUTABLE test cases that a test automation framework can run.

Output JSON in this EXACT shape:

{{
  "start_url": "the URL where tests should begin (usually page_0's URL)",
  "test_cases": [
    {{
      "id": "TC_<FEATURE>_<SCENARIO>_<NUMBER> (e.g., TC_LOGIN_VALID_01)",
      "name": "Short descriptive name",
      "description": "What user flow this tests and expected outcome",
      "preconditions": ["List of conditions that must be true before test starts"],
      "tags": ["functional", "happy_path|negative|edge_case", "priority_high|medium|low"],
      "current_page": "page_id where test starts (after navigation)",
      "steps": [
        {{
          "step_number": 1,
          "page_id": "MUST be your current page - the page you are on when executing this step",
          "action": "navigate|click|type|clear|select|assert|wait|hover|scroll",
          "target_element_key": "EXACT key from the page's element list, or null for navigate/wait",
          "input_value": "REQUIRED for type/select: the EXACT concrete value to enter. NEVER null. Use 'NeedToAsk: <desc>' only when the value is truly unknown.",
          "expected_result": "What should happen after this step (e.g., 'Page navigates to login', 'Error message appears')",
          "details": "Additional context for code generation"
        }}
      ],
      "expected_final_state": "Description of the expected state after all steps complete",
      "covered_elements": [
        {{
          "page_id": "page_x",
          "key": "EXACT element key from that page's list",
          "interaction_type": "click|type|assert|hover",
          "description": "What this element does in the test"
        }}
      ]
    }}
  ],
  "coverage_summary": "Paragraph explaining test coverage and any gaps"
}}

=== CRITICAL CONSTRAINTS ===
1. Create 5-10 comprehensive test cases covering:
   - Happy path flows (valid inputs, successful navigation)
   - Negative tests (invalid inputs, error handling)
   - Boundary/edge cases (empty fields, special characters)
   - Navigation tests (verify links work correctly)

2. PAGE TRACKING:
   - Track your "current_page" as you design steps
   - After a click on a navigation edge, your current_page CHANGES to the destination
   - You can ONLY use elements from your current_page
   - NEVER assert on elements from a page you're not on

3. ELEMENT KEYS:
   - Copy keys EXACTLY from the element lists (including trailing |)
   - For inputs: use the key that includes name and type (e.g., "input|||email|email|")
   - Match the full key format shown in the page elements

4. STEP COMPLETENESS:
   - Each step must have: step_number, page_id, action, expected_result
   - For type actions: include input_value
   - For assertions: include what you're verifying in expected_result
   - Include wait steps after navigation for page loads

5. ASSERTIONS:
   - Assert on page-specific elements (forms, headings, unique content)
   - Avoid asserting on global navigation elements (they exist on all pages)
   - Use assert to verify: page loaded, element visible, text content, form state

6. SUBMIT OUTCOMES MUST MATCH THE TEST TYPE:
    - Happy path / valid-data tests: success modal is expected.
    - Negative / edge / validation / special-character tests: do NOT assume success modal.
    - For those tests, prefer post-submit asserts like "form still visible", "field still present/value kept",
      or "submission blocked".

=== TEST DATA GUIDE — Use these values in "input_value" for Practice Form fields ===
  #firstName          → "Alice"
  #lastName           → "Johnson"
  #userEmail          → "alice.johnson@test.com"
  #userNumber         → "1234567890"   (exactly 10 digits)
  #dateOfBirthInput   → "10 Sep 1990"  (format: dd mmm yyyy)
  #subjectsAutocomplete → "Maths"      (MUST be an exact subject name from the list above)
  State dropdown      → "NCR"
  City dropdown       → "Delhi"        (valid city for NCR state)
  #currentAddress     → "123 Main Street, Cityville"
  Gender radio ids    → gender_0=Male  gender_1=Female  gender_2=Other
  Hobbies checkbox ids→ hobbies_0=Sports  hobbies_1=Reading  hobbies_2=Music

  For NEGATIVE tests:
    Invalid email   → "invalid-email-format"
    Short mobile    → "123"       (too short)
    Long mobile     → "12345678901"  (11 digits — over maxlength)
    Special chars   → "Élise!@#"  (for name / address fields)
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
        # Start tracking Phase 1 only if not already started by the agent explorer
        if not self._metrics.get_current_phase_name():
            self._metrics.start_phase(PHASE_EXPLORATION)

        json_plan = self._ask_llm_for_plan(graph, human_feedback)
        json_plan = self._validate_and_fix_plan(json_plan, graph)
        element_lookup = self._build_element_lookup(graph)

        test_cases: List[TestCase] = []
        coverage: Dict[str, List[str]] = {}
        start_url = json_plan.get("start_url")

        for tc_json in json_plan.get("test_cases", []):
            steps: List[TestStep] = []
            for st in tc_json.get("steps", []):
                page_id = st.get("page_id", "")
                raw_target = st.get("target_element_key")
                
                # Resolve the target element to get actual selectors
                resolved_target = None
                css_selector = None
                playwright_locator = None
                
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
                            css_selector = elem.css_selector
                            playwright_locator = elem_info.get("playwright_locator")
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
                        step_number=st.get("step_number"),
                        page_url=st.get("page_url"),
                        input_value=st.get("input_value"),
                        expected_result=st.get("expected_result"),
                        css_selector=css_selector,
                        playwright_locator=playwright_locator,
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
                preconditions=tc_json.get("preconditions", []),
                expected_final_state=tc_json.get("expected_final_state"),
                start_url=start_url,
                final_page_id=tc_json.get("final_page"),
            )
            test_cases.append(tc)

        # Build pages info
        pages: Dict[str, Dict[str, str]] = {}
        for page_id, node in graph.pages.items():
            snap = node.snapshot
            pages[page_id] = {"url": snap.url, "title": snap.title}

        # End Phase 1 tracking
        self._metrics.end_phase()

        return {
            "test_cases": test_cases,
            "coverage": coverage,
            "pages": pages,
            "start_url": start_url,
            "coverage_summary": json_plan.get("coverage_summary"),
        }
