from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .element_descriptor import ElementDescriptor

@dataclass
class PageSnapshot:
    """
    A structured summary of a single page after exploration.
    This is the Phase 1 output that feeds Phase 2+.
    """
    url: str
    title: str
    raw_html: str
    elements: List[ElementDescriptor] = field(default_factory=list)

    screenshot_path: Optional[str] = None

    # Optional: high-level LLM summary of the page (bergoula fakes mout be deepseek-coder bas hanshouf)
    summary: Optional[str] = None

    # Extra metadata (response time, etc.)
    meta: Dict[str, str] = field(default_factory=dict)
