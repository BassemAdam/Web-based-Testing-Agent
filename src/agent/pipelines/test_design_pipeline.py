from __future__ import annotations
from typing import List, Dict, Optional
import json

from ..llm.ollama_client import LLMClient
from ..models.page_snapshot import PageSnapshot
from ..models.test_case import TestCase, TestStep
from ..models.test_plan import TestPlan

class TestDesignPipeline:
    """
    Phase 2: given a PageSnapshot, propose a logical test plan
    and compute element coverage.
    Supports refinement based on human feedback.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.llm = LLMClient(model=model_name)

    @staticmethod
    def _element_key(tag: str, text: str, element_id: str) -> str:
        text = (text or "").strip()
        element_id = element_id or ""
        return f"{tag}|{text}|{element_id}"

    def _canonical_key(self,raw_key: str) -> str:
        """
        Normalize element keys coming from the LLM.

        If the LLM returns something like:
        "a|Learn more| | tag=a, text='Learn more', id='', name=None, type=None, css='a'"
        we keep only the first part before " | tag=":
        "a|Learn more|"
        """
        if not raw_key:
            return ""
        return raw_key.split(" | tag=", 1)[0].strip()

    
    def _build_elements_preview(self, snapshot: PageSnapshot) -> str:
        lines = []
        for e in snapshot.elements[:40]:  # keep prompt small
            key = self._element_key(e.tag, e.text, e.id)
            lines.append(
                f"- key={key} | tag={e.tag}, text={e.text!r}, id={e.id!r}, "
                f"name={e.name!r}, type={e.type!r}, css={e.css_selector!r}"
            )
        return "\n".join(lines) or "(no interactive elements detected)"

    def _propose_plan_json(
        self,
        snapshot: PageSnapshot,
        human_feedback: Optional[str] = None
    ) -> Dict:
        """
        Ask the LLM to propose a test plan in JSON.
        Returns a Python dict.
        """
        elements_preview = self._build_elements_preview(snapshot)
        feedback_text = human_feedback or "No feedback yet. Propose an initial plan."

        system_msg = """
You are a senior QA engineer collaborating with a human tester.
You design HIGH-LEVEL logical test cases (not code) for a single web page.

Rules:
- You do NOT browse. You only know the page from the given summary and elements.
- Focus on meaningful user flows and edge cases.
- Think like someone planning tests BEFORE automation.
- Output STRICTLY valid JSON according to the requested schema.
- Do NOT include explanations outside the JSON.
""".strip()

        # You can also feed snapshot.summary if present
        snapshot_summary = snapshot.summary or "(no summary available)"

        user_msg = f"""
We have this web page:

Title: {snapshot.title}
URL: {snapshot.url}

High-level page summary:
\"\"\"summary
{snapshot_summary}
\"\"\"

Interactive elements on the page (each has a 'key' that uniquely identifies it):
{elements_preview}

The human has given this feedback:
\"\"\"feedback
{feedback_text}
\"\"\"

Design a TEST PLAN as JSON with the following shape:

{{
  "test_cases": [
    {{
      "id": "string (e.g., TC_LOGIN_VALID_01)",
      "name": "short descriptive name",
      "description": "what scenario this test covers",
      "tags": ["functional", "happy_path", "..."],
      "steps": [
        {{
          "action": "click|type|assert|navigate|other",
          "target_element_key": "one of the element keys above or null",
          "details": "more detail about the step (e.g., input value, assert condition)"
        }}
      ],
      "covered_element_keys": ["list of element keys that this test touches"]
    }}
  ],
  "coverage_summary": "short paragraph explaining coverage and notable gaps"
}}

Requirements:
- Use element keys from the list whenever you refer to UI elements.
- Make 5–10 test cases (depending on page complexity).
- Include both happy-path and edge-case / negative tests where applicable.
- Return ONLY the JSON object, no extra text.
""".strip()

        raw = self.llm.chat(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=4096,
            temperature=0.2,
        )

        # Basic safety: try to parse JSON, optionally strip junk around it
        raw_str = raw.strip()
        # If model wrapped JSON in ```json blocks, strip them
        if raw_str.startswith("```"):
            raw_str = raw_str.strip("`")
            # remove possible "json\n" prefix
            if raw_str.lower().startswith("json"):
                raw_str = raw_str[4:].lstrip()

        try:
            data = json.loads(raw_str)
        except json.JSONDecodeError:
            # In Phase 2 we can later add a "repair JSON" step.
            raise ValueError(f"LLM returned invalid JSON:\n{raw_str}")

        return data

    def _build_test_plan_from_json(self, snapshot: PageSnapshot, plan_json: Dict) -> TestPlan:
        test_cases: List[TestCase] = []
        coverage_map: Dict[str, List[str]] = {}

        for tc_json in plan_json.get("test_cases", []):
            steps: List[TestStep] = []
            for st in tc_json.get("steps", []):
                steps.append(
                    TestStep(
                        action=st.get("action", ""),
                        target=st.get("target_element_key"),
                        details=st.get("details"),
                    )
                )

            raw_keys = tc_json.get("covered_element_keys", [])
            canon_keys = [self._canonical_key(k) for k in raw_keys]

            tc = TestCase(
                id=tc_json.get("id", ""),
                name=tc_json.get("name", ""),
                description=tc_json.get("description", ""),
                tags=tc_json.get("tags", []),
                steps=steps,
                covered_element_keys=canon_keys,
            )
            test_cases.append(tc)

            # build coverage map using canonical keys
            for key in canon_keys:
                if not key:
                    continue
                coverage_map.setdefault(key, []).append(tc.id)

        plan = TestPlan(
            snapshot=snapshot,
            test_cases=test_cases,
            element_coverage=coverage_map,
            coverage_summary=plan_json.get("coverage_summary"),
        )
        return plan


    def propose_plan(
        self,
        snapshot: PageSnapshot,
        human_feedback: Optional[str] = None
    ) -> TestPlan:
        """
        Public entry: given a snapshot + optional textual feedback from the human,
        propose a new TestPlan.
        """
        plan_json = self._propose_plan_json(snapshot, human_feedback)
        return self._build_test_plan_from_json(snapshot, plan_json)
