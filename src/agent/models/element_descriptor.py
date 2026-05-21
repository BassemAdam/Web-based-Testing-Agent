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

    # CSS class/selector fragments that indicate a navigation or sidebar zone.
    _NAV_PATTERNS = (
        "nav", "navbar", "sidebar", "side-bar", "side-nav", "sidenav",
        "header", "topbar", "top-bar", "footer", "breadcrumb",
        "navigation", "menu", "menubar", "site-menu", "main-menu",
    )

    def is_nav_or_sidebar(self) -> bool:
        """
        Return True when this element is likely part of a navbar, sidebar,
        header, footer, or breadcrumb rather than the main page content.
        Checks the element's own CSS classes, css_selector, and aria_label.
        """
        patterns = self._NAV_PATTERNS
        for cls in self.classes:
            cls_lower = cls.lower()
            if any(p in cls_lower for p in patterns):
                return True
        if self.css_selector:
            sel_lower = self.css_selector.lower()
            if any(p in sel_lower for p in patterns):
                return True
        if self.aria_label:
            lbl = self.aria_label.lower()
            if any(p in lbl for p in ("navigation", "menu", "sidebar")):
                return True
        return False

    def short_description(self) -> str:
        parts = [self.tag]
        if self.id:
            parts.append(f"#{self.id}")
        if self.text:
            parts.append(f'"{self.text[:30]}"')
        return " ".join(parts)
