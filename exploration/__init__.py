"""
Phase 1: Web Page Exploration & Knowledge Acquisition Module

This module contains tools and agents for deep web page understanding:
- DOM structure analysis
- Visual element detection via screenshots
- Interactive exploration capabilities
- Structured page representation output
"""

from .models import PageStructure, ElementCandidate, VisualSignature
from .agent import PageExplorerAgent

__all__ = [
    "PageStructure",
    "ElementCandidate", 
    "VisualSignature",
    "PageExplorerAgent"
]
