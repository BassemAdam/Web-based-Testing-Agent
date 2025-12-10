# src/agent/models/test_plan.py
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from .test_case import TestCase
from .page_snapshot import PageSnapshot

@dataclass
class TestPlan:
    """
    Phase 2 artifact: list of logical test cases + coverage info
    derived from a single PageSnapshot.
    """
    snapshot: PageSnapshot
    test_cases: List[TestCase] = field(default_factory=list)

    # element_key -> list of test case ids that touch it
    element_coverage: Dict[str, List[str]] = field(default_factory=dict)

    # free-form summary of coverage (e.g., from LLM)
    coverage_summary: Optional[str] = None

    def to_dict(self) -> Dict:
        """
        Flatten to a JSON-friendly dict (PageSnapshot is already a dataclass).
        """
        data = {
            "snapshot": asdict(self.snapshot),
            "test_cases": [asdict(tc) for tc in self.test_cases],
            "element_coverage": self.element_coverage,
            "coverage_summary": self.coverage_summary,
        }
        return data
