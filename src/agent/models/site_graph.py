# src/agent/models/site_graph.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .page_snapshot import PageSnapshot

@dataclass
class NavEdge:
    """An interaction that took us from one page to another."""
    from_page_id: str
    to_page_id: str
    element_key: str           # key of the element that was clicked
    description: str           # human readable, optional


@dataclass
class PageNode:
    """A node in the site graph = one visited page."""
    id: str                    # e.g. "page_0", "page_1"
    snapshot: PageSnapshot
    incoming_edge: Optional[NavEdge] = None


@dataclass
class SiteGraph:
    """A small explored portion of the site."""
    pages: Dict[str, PageNode] = field(default_factory=dict)
    edges: List[NavEdge] = field(default_factory=list)
