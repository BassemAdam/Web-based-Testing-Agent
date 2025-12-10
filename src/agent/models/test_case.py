from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class TestStep:
    """
    A single step in a logical test case, at the UI / scenario level
    (not yet bound to concrete automation code).
    """
    action: str                    # e.g., "click", "type", "assert"
    page_id: str                   # which page we are on in the graph 
    target: Optional[str] = None   # logical target id, or element description
    details: Optional[str] = None  # e.g., input value, expected condition


@dataclass
class SelectorInfo:
    """
    Selector details for an element used in a test case.
    """
    element_key: str               # e.g., "a|Learn more|"
    page_id: str                   # which page this element belongs to
    css_selector: Optional[str] = None
    xpath: Optional[str] = None
    description: str = ""          # short description of what this element does


@dataclass
class TestCase:
    """
    Logical test case (Phase 2). This is what the human & AI negotiate about.
    """
    id: str                         # logical id like "TC_LOGIN_VALID_01"
    name: str                       # human-readable title
    description: str                # short description / intent
    tags: List[str] = field(default_factory=list)
    steps: List[TestStep] = field(default_factory=list)

    # Optional mapping to elements from PageSnapshot for coverage
    covered_element_keys: List[str] = field(default_factory=list)
    # e.g., ["a|Learn more|", "button|Submit|#submit-btn"]

    # Selectors with descriptions for each element used in this test
    selectors: List[SelectorInfo] = field(default_factory=list)

    meta: Dict[str, str] = field(default_factory=dict)