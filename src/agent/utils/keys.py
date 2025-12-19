from __future__ import annotations
from ..models.element_descriptor import ElementDescriptor


def build_element_key(
    tag: str, 
    text: str, 
    id: str, 
    name: str = None, 
    input_type: str = None
) -> str:
    """
    Build a unique key for an element.
    Format: tag|text|id|name|type
    
    For inputs, includes name and type to distinguish between:
    - email input: input|||email|email
    - password input: input|||password|password  
    - checkbox: input|||remember|checkbox
    """
    parts = [
        tag or "",
        (text or "").strip()[:50],  # Truncate long text
        id or "",
    ]
    
    # For form elements, add name and type for uniqueness
    if tag in ["input", "select", "textarea"]:
        parts.append(name or "")
        parts.append(input_type or "")
    
    return "|".join(parts)
def canonicalize_key(raw_key: str) -> str:
    """
    Normalize element key for comparison.
    Handles variations in whitespace and trailing pipes.
    """
    # Strip whitespace from each part
    parts = raw_key.split("|")
    cleaned = [p.strip() for p in parts]
    
    # Remove trailing empty parts
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    
    return "|".join(cleaned)

def key_from_descriptor(e: ElementDescriptor) -> str:
    """
    Build a canonical key from an ElementDescriptor.
    """
    return build_element_key(e.tag, e.text, e.id)


def canonicalize_key(raw: str) -> str:
    """
    Normalize any key we get from the LLM / coverage data into the
    canonical form tag|text|id.

    Handles inputs like:
      "page_0::a|Learn more"
      "a|Learn more"
      "a|Learn more|"
      "a|Learn more| | tag=a, text='Learn more', id='', ..."
    """
    if not raw:
        return ""

    # Drop page prefix if present: "page_0::a|Learn more" -> "a|Learn more"
    if "::" in raw:
        _, raw = raw.split("::", 1)

    # Drop any extra description the LLM may have appended
    raw = raw.split(" | tag=", 1)[0].strip()

    parts = raw.split("|")
    tag = parts[0] if len(parts) > 0 else ""
    text = parts[1] if len(parts) > 1 else ""
    element_id = parts[2] if len(parts) > 2 else ""

    return f"{tag}|{text}|{element_id}"
