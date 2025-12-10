from __future__ import annotations
from ..models.element_descriptor import ElementDescriptor


def build_element_key(tag: str, text: str | None, element_id: str | None) -> str:
    """
    Build our canonical internal key in the form: tag|text|id
    where id may be empty string.
    """
    text = (text or "").strip()
    element_id = element_id or ""
    return f"{tag}|{text}|{element_id}"


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
