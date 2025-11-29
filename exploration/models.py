"""
Structured output models for Page Exploration (Phase 1)

These models represent the "ground truth" knowledge acquired about a web page.
They capture enough detail for future test generation and self-healing capabilities.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal


class VisualSignature(BaseModel):
    """Visual characteristics of an element for self-healing capabilities."""
    screenshot_base64: Optional[str] = Field(None, description="Base64 encoded screenshot of the element")
    bounding_box: Optional[Dict[str, float]] = Field(None, description="x, y, width, height coordinates")
    visible_text: Optional[str] = Field(None, description="Text visible in/near the element")
    background_color: Optional[str] = Field(None, description="Background color if detectable")
    font_info: Optional[str] = Field(None, description="Font family, size, weight if detectable")


class ElementCandidate(BaseModel):
    """
    Represents a testable element discovered during exploration.
    Contains multiple locator strategies for robustness and self-healing.
    """
    element_id: str = Field(..., description="Unique identifier for this element")
    element_type: str = Field(..., description="Type of element: button, input, link, form, etc.")
    
    # Multiple locator strategies (for self-healing)
    locators: Dict[str, str] = Field(
        default_factory=dict,
        description="Multiple ways to find this element: css, xpath, text, role, etc."
    )
    
    # Semantic information
    description: str = Field(..., description="What this element does or represents")
    semantic_role: Optional[str] = Field(None, description="ARIA role or semantic purpose")
    
    # Context information
    parent_context: Optional[str] = Field(None, description="Parent element or section")
    nearby_elements: List[str] = Field(default_factory=list, description="IDs of related elements")
    
    # Visual information for self-healing
    visual_signature: Optional[VisualSignature] = Field(None, description="Visual characteristics")
    
    # Interaction capabilities
    is_interactive: bool = Field(False, description="Can this element be clicked/filled?")
    expected_actions: List[str] = Field(
        default_factory=list,
        description="Possible actions: click, fill, hover, etc."
    )
    
    # State information
    initial_state: Optional[Dict[str, Any]] = Field(
        None,
        description="Initial attributes: value, checked, disabled, etc."
    )


class PageSection(BaseModel):
    """Logical grouping of related elements (e.g., navigation bar, form, footer)."""
    section_id: str = Field(..., description="Unique identifier for this section")
    section_type: str = Field(..., description="Type: header, navigation, form, content, footer, etc.")
    description: str = Field(..., description="What this section contains/does")
    elements: List[str] = Field(default_factory=list, description="IDs of elements in this section")


class InteractionFlow(BaseModel):
    """Detected multi-step interaction patterns (e.g., login flow, checkout)."""
    flow_id: str = Field(..., description="Unique identifier for this flow")
    flow_name: str = Field(..., description="Name of the flow: login, search, checkout, etc.")
    steps: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Ordered steps in the flow with element IDs and actions"
    )
    entry_point: str = Field(..., description="Element ID where flow starts")
    success_indicator: Optional[str] = Field(None, description="How to verify flow succeeded")


class PageStructure(BaseModel):
    """
    Complete structured representation of a web page.
    This is the "ground truth" output from Phase 1 exploration.
    """
    url: str = Field(..., description="The URL that was explored")
    page_title: str = Field(..., description="Page title")
    exploration_timestamp: str = Field(..., description="When this exploration was performed")
    
    # Core structural data
    elements: List[ElementCandidate] = Field(
        default_factory=list,
        description="All discovered testable elements"
    )
    
    sections: List[PageSection] = Field(
        default_factory=list,
        description="Logical page sections grouping related elements"
    )
    
    flows: List[InteractionFlow] = Field(
        default_factory=list,
        description="Detected multi-step interaction patterns"
    )
    
    # Page-level metadata
    dom_structure_summary: Optional[str] = Field(
        None,
        description="High-level summary of DOM structure"
    )
    
    full_page_screenshot: Optional[str] = Field(
        None,
        description="Base64 encoded screenshot of entire page"
    )
    
    accessibility_tree: Optional[str] = Field(
        None,
        description="Accessibility tree representation for semantic understanding"
    )
    
    # Discovery metadata
    exploration_strategy: str = Field(
        "hybrid",
        description="Strategy used: dom_only, visual_only, hybrid, interactive"
    )
    
    total_elements_found: int = Field(0, description="Count of elements discovered")
    exploration_depth: int = Field(0, description="How many levels deep the exploration went")
    
    # Additional insights
    technologies_detected: List[str] = Field(
        default_factory=list,
        description="Detected frameworks/libraries: React, Vue, Angular, etc."
    )
    
    dynamic_content_areas: List[str] = Field(
        default_factory=list,
        description="Areas that appear to load dynamically"
    )

    def to_json_file(self, filepath: str):
        """Save the page structure to a JSON file."""
        import json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json_file(cls, filepath: str):
        """Load page structure from a JSON file."""
        import json
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)
