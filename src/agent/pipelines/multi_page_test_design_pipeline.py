from __future__ import annotations
import json
from collections import Counter, deque
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

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

    def _validate_and_fix_plan(self, json_plan: Dict, graph: SiteGraph) -> Dict:
        """
        Enforce page coherence and element validity against the graph.
        """
        element_lookup = self._build_element_lookup(graph)
        page_keys = self._build_page_key_map(element_lookup)
        explicit_edges = self._build_edge_map(graph)
        inferred_edges = self._build_inferred_edge_map(graph, page_keys)
        edge_map = self._merge_edge_maps(explicit_edges, inferred_edges)
        key_frequency = self._build_key_frequency(page_keys)
        page_markers = self._build_page_markers(graph, element_lookup, page_keys, key_frequency)
        email_inputs: Dict[str, List[str]] = {}
        for info in element_lookup.values():
            elem = info.get("element")
            page_id = info.get("page_id")
            if not elem or not page_id:
                continue
            if elem.tag == "input" and elem.type == "email":
                email_inputs.setdefault(page_id, []).append(info.get("element_key"))
        start_page_id = self._find_start_page_id(graph, json_plan.get("start_url"))

        for tc_json in json_plan.get("test_cases", []):
            current_page = start_page_id
            new_steps: List[Dict] = []
            covered_map: Dict[str, Dict] = {}
            typed_email_pages = set()

            tc_text = f"{tc_json.get('name', '')} {tc_json.get('description', '')}".lower()
            needs_invalid_email = "invalid" in tc_text and "email" in tc_text and "empty" not in tc_text

            def add_step(step: Dict) -> None:
                if (
                    step.get("action") == "assert"
                    and new_steps
                    and new_steps[-1].get("action") == "assert"
                    and new_steps[-1].get("target_element_key") == step.get("target_element_key")
                ):
                    return
                new_steps.append(step)

            def add_page_assert(page_id: str) -> None:
                for step in self._page_assertion_steps(graph, page_id, page_markers):
                    add_step(step)

            if current_page:
                add_page_assert(current_page)

            for st in tc_json.get("steps", []):
                action = st.get("action", "")
                page_id = st.get("page_id") or current_page
                raw_target = st.get("target_element_key")
                details = st.get("details")

                if page_id not in graph.pages:
                    page_id = current_page

                if action == "navigate":
                    if page_id and page_id in graph.pages:
                        current_page = page_id
                        add_step(
                            {
                                "page_id": page_id,
                                "action": action,
                                "target_element_key": None,
                                "details": details,
                            }
                        )
                        add_page_assert(page_id)
                    continue

                if current_page and page_id and page_id != current_page:
                    nav_path = self._find_navigation_path(current_page, page_id, edge_map)
                    if not nav_path:
                        continue
                    for nav_step in nav_path:
                        add_step(
                            {
                                "page_id": nav_step["from"],
                                "action": "click",
                                "target_element_key": nav_step["key"],
                                "details": f"Navigate to {nav_step['dest']}",
                            }
                        )
                        current_page = nav_step["dest"]
                        add_page_assert(current_page)

                resolved_key = self._resolve_key(page_id, raw_target, page_keys) if raw_target else None
                if raw_target and not resolved_key:
                    elem_info = self._fuzzy_find_element(element_lookup, page_id, raw_target)
                    if elem_info:
                        resolved_key = elem_info.get("element_key")

                if action == "assert":
                    if not resolved_key or self._is_weak_assert(page_id, resolved_key, key_frequency, element_lookup):
                        resolved_key = page_markers.get(page_id) or resolved_key
                    if not resolved_key:
                        continue

                if raw_target and not resolved_key:
                    continue

                if action == "type" and resolved_key:
                    if resolved_key in (email_inputs.get(page_id) or []):
                        typed_email_pages.add(page_id)

                if action == "click" and resolved_key and needs_invalid_email:
                    if page_id in email_inputs and page_id not in typed_email_pages:
                        info = element_lookup.get(f"{page_id}::{resolved_key}")
                        if info and self._is_submit_like(info.get("element")):
                            email_key = email_inputs[page_id][0]
                            add_step(
                                {
                                    "page_id": page_id,
                                    "action": "type",
                                    "target_element_key": email_key,
                                    "details": "Enter invalid email value: invalid-email",
                                }
                            )
                            typed_email_pages.add(page_id)

                add_step(
                    {
                        "page_id": page_id,
                        "action": action,
                        "target_element_key": resolved_key,
                        "details": details,
                    }
                )

                if action == "click" and resolved_key and current_page:
                    edge_info = edge_map.get(current_page, {}).get(canonicalize_key(resolved_key))
                    if edge_info:
                        current_page = edge_info.get("dest")
                        if current_page:
                            add_page_assert(current_page)

            if current_page and (not new_steps or new_steps[-1].get("action") != "assert"):
                add_page_assert(current_page)

            tc_json["steps"] = new_steps

            for ce in tc_json.get("covered_elements", []):
                pid = ce.get("page_id")
                raw_key = ce.get("key")
                if pid not in graph.pages:
                    continue
                resolved = self._resolve_key(pid, raw_key, page_keys)
                if not resolved:
                    continue
                ce["key"] = resolved
                covered_map[f"{pid}::{resolved}"] = ce

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
                    "description": f"Used for {step.get('action')} step",
                }

            tc_json["covered_elements"] = list(covered_map.values())

        return json_plan
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
        feedback = human_feedback or "No feedback yet. Propose 3-8 good tests."

        system_msg = """
You are a senior QA engineer collaborating with a human tester.
You design HIGH-LEVEL logical test cases that may span MULTIPLE PAGES.

Rules:
- You DO NOT browse. You only know the site from the given pages and navigation edges.
- Focus on realistic user flows (e.g., sign in, basic navigation, search).
- Include both happy-path and negative/edge tests.
- Keep steps in a coherent order; do not jump between pages without navigation.
- Prefer assertions on elements that are specific to the target page (avoid global header links).
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
- Do not reference elements from other pages; only move pages by clicking an edge element or using navigate.
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
        json_plan = self._validate_and_fix_plan(json_plan, graph)
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
