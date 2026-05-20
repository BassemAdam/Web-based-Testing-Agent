from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class ElementDescriptor:
    """
    Representation of ground truth UI elements which will be used in other phases
    """
    id: str
    tag: str
    text: str
    role: Optional[str] = None
    aria_label: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None

    # Locators we could use in POM / tests later
    css_selector: Optional[str] = None
    xpath: Optional[str] = None

    # Additional attributes for self-healing / visual match later
    attributes: Dict[str, str] = field(default_factory=dict)
    classes: List[str] = field(default_factory=list)

    # Where it is in the page
    bounding_box: Optional[Dict[str, float]] = None  # {x, y, width, height}

    def short_description(self) -> str:
        parts = [self.tag]
        if self.id:
            parts.append(f"#{self.id}")
        if self.text:
            parts.append(f'"{self.text[:30]}"')
        return " ".join(parts)
