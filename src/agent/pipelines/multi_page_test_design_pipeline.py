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
        Build a lookup: "page_id::element_key" -> element info (css, xpath, description)
        Also builds a secondary lookup by partial key for fuzzy matching.
        """
        lookup = {}
        for page_id, node in graph.pages.items():
            for e in node.snapshot.elements:
                key = build_element_key(e.tag, e.text, e.id)
                full_key = f"{page_id}::{key}"
                lookup[full_key] = {
                    "element_key": key,
                    "page_id": page_id,
                    "css_selector": e.css_selector,
                    "xpath": e.xpath,
                    "description": e.short_description(),
                    "element": e,  # Keep reference for fuzzy matching
                }
        return lookup

    def _fuzzy_find_element(
        self, 
        lookup: Dict[str, Dict], 
        page_id: str, 
        raw_key: str
    ) -> Optional[Dict]:
        """
        Try to find an element in the lookup, with fuzzy matching fallback.
        """
        canon_key = canonicalize_key(raw_key)
        full_key = f"{page_id}::{canon_key}"
        
        # Exact match
        if full_key in lookup:
            return lookup[full_key]
        
        # Fuzzy match: find elements where the key starts with or contains the search text
        search_parts = canon_key.split("|")
        search_tag = search_parts[0] if search_parts else ""
        search_text = search_parts[1] if len(search_parts) > 1 else ""
        
        for key, info in lookup.items():
            if not key.startswith(f"{page_id}::"):
                continue
            elem_key = info["element_key"]
            elem_parts = elem_key.split("|")
            elem_tag = elem_parts[0] if elem_parts else ""
            elem_text = elem_parts[1] if len(elem_parts) > 1 else ""
            
            # Match if same tag and text starts with or contains search text
            if elem_tag == search_tag:
                if search_text and (
                    elem_text.startswith(search_text) or 
                    search_text in elem_text or
                    elem_text in search_text
                ):
                    return info
        
        return None

    def _build_graph_preview(self, graph: SiteGraph) -> str:
       
        lines: List[str] = []

        for page_id, node in graph.pages.items():
            snap = node.snapshot
            lines.append(f"Page {page_id}: {snap.title} [{snap.url}]")
            # show a few elements
            for e in snap.elements[:8]:
                key = build_element_key(e.tag, e.text, e.id)
                lines.append(
                    f"  - key={key} | tag={e.tag}, text={e.text!r}, id={e.id!r}, css={e.css_selector!r}"
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
        """
        Return a dict with:
          - "test_cases": serialized TestCase objects
          - "coverage": { "<page_id>::<key>": [test_ids...] }
          - "coverage_summary": string
        """
        json_plan = self._ask_llm_for_plan(graph, human_feedback)

        # Build element lookup for selectors
        element_lookup = self._build_element_lookup(graph)

        test_cases: List[TestCase] = []
        coverage: Dict[str, List[str]] = {}

        for tc_json in json_plan.get("test_cases", []):
            steps: List[TestStep] = []
            for st in tc_json.get("steps", []):
                page_id = st.get("page_id", "")
                tkey = st.get("target_element_key")
                steps.append(
                    TestStep(
                        action=st.get("action", ""),
                        page_id=page_id,
                        target=tkey,
                        details=st.get("details"),
                    )
                )

            # normalize covered elements and build selectors
            covered_pairs = []
            selectors: List[SelectorInfo] = []

            for ce in tc_json.get("covered_elements", []):
                pid = ce.get("page_id", "")
                raw_key = ce.get("key", "")
                canon_key = canonicalize_key(raw_key)
                llm_description = ce.get("description", "")

                if pid and canon_key:
                    covered_pairs.append((pid, canon_key))
                    cov_key = f"{pid}::{canon_key}"
                    coverage.setdefault(cov_key, []).append(tc_json.get("id", ""))

                    # Look up element info with fuzzy matching
                    elem_info = self._fuzzy_find_element(element_lookup, pid, raw_key)
                    if elem_info:
                        selectors.append(
                            SelectorInfo(
                                element_key=elem_info["element_key"],
                                page_id=pid,
                                css_selector=elem_info.get("css_selector"),
                                xpath=elem_info.get("xpath"),
                                description=llm_description or elem_info.get("description", ""),
                            )
                        )
                    else:
                        # Element not found - still add with nulls
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