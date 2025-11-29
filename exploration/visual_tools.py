"""
Visual Analysis Tools for Phase 1 Exploration

These tools help the agent "see" the page through screenshots and visual analysis,
complementing the DOM-based understanding.
"""

from tools.decorator import tool
from browser_manager import get_page
from loguru import logger
import json
import base64


@tool()
def take_full_page_screenshot(session_id: str = "default") -> str:
    """
    Take a full-page screenshot and return as base64.
    This provides visual context for the entire page.
    
    Returns: Base64 encoded PNG image with data URI prefix.
    """
    logger.debug(f"[take_full_page_screenshot] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        screenshot_bytes = page.screenshot(full_page=True)
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
        return f"data:image/png;base64,{base64_image}"
    except Exception as e:
        logger.error(f"Failed to take full page screenshot: {e}")
        return json.dumps({"error": str(e)})


@tool()
def take_element_screenshot(selector: str, session_id: str = "default") -> str:
    """
    Take a screenshot of a specific element.
    Useful for creating visual signatures for self-healing.
    
    Args:
        selector: CSS selector, text=, or role= for the element
        session_id: Browser session identifier
    
    Returns: Base64 encoded PNG image with data URI prefix.
    """
    logger.debug(f"[take_element_screenshot] selector={selector}, session_id={session_id}")
    page = get_page(session_id)
    
    try:
        # Determine locator strategy
        if selector.startswith("text="):
            element = page.get_by_text(selector[5:], exact=False).first
        elif selector.startswith("role="):
            role_part = selector[5:]
            role_split = role_part.split(" name=")
            role_name = role_split[0]
            role_label = role_split[1] if len(role_split) > 1 else None
            element = page.get_by_role(role_name, name=role_label).first
        else:
            element = page.locator(selector).first
        
        screenshot_bytes = element.screenshot()
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
        return f"data:image/png;base64,{base64_image}"
    
    except Exception as e:
        logger.error(f"Failed to take element screenshot for '{selector}': {e}")
        return json.dumps({"error": str(e)})


@tool()
def extract_visual_layout(session_id: str = "default") -> str:
    """
    Extract visual layout information: element positions, colors, visibility.
    This helps understand the visual hierarchy and grouping.
    
    Returns: JSON string with visual layout data.
    """
    logger.debug(f"[extract_visual_layout] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const layout = {
                viewport: {
                    width: window.innerWidth,
                    height: window.innerHeight,
                    scroll_height: document.documentElement.scrollHeight
                },
                visual_elements: []
            };
            
            // Get all visible elements with significant size
            const allElements = document.querySelectorAll('*');
            
            allElements.forEach((el, idx) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                
                // Only include visible elements with reasonable size
                if (style.display === 'none' || style.visibility === 'hidden' ||
                    rect.width < 10 || rect.height < 10) {
                    return;
                }
                
                // Only capture meaningful elements (not every div)
                const meaningfulTags = ['button', 'a', 'input', 'select', 'textarea', 
                                       'img', 'video', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                                       'p', 'form', 'nav', 'header', 'footer', 'article'];
                
                const hasMeaningfulContent = el.innerText?.trim() || 
                                            el.src || 
                                            el.href ||
                                            meaningfulTags.includes(el.tagName.toLowerCase());
                
                if (!hasMeaningfulContent) return;
                
                const visualInfo = {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    position: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        top: Math.round(rect.top),
                        bottom: Math.round(rect.bottom)
                    },
                    styling: {
                        background_color: style.backgroundColor,
                        color: style.color,
                        font_size: style.fontSize,
                        font_weight: style.fontWeight,
                        font_family: style.fontFamily,
                        border: style.border,
                        z_index: style.zIndex
                    },
                    text_preview: el.innerText?.trim().substring(0, 50) || null,
                    is_interactive: ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA']
                        .includes(el.tagName)
                };
                
                layout.visual_elements.push(visualInfo);
            });
            
            return layout;
        }
        """
        
        layout = page.evaluate(js_code)
        return json.dumps(layout, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to extract visual layout: {e}")
        return json.dumps({"error": str(e)})


@tool()
def detect_visual_groups(session_id: str = "default") -> str:
    """
    Detect visual groupings based on proximity and styling.
    Elements that are visually close and similarly styled likely form a group.
    
    Returns: JSON string with detected visual groups.
    """
    logger.debug(f"[detect_visual_groups] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const groups = [];
            
            // Find containers that have multiple interactive children
            const containers = document.querySelectorAll('div, section, nav, form, ul, ol');
            
            containers.forEach((container, idx) => {
                const interactiveChildren = container.querySelectorAll(
                    ':scope > button, :scope > a, :scope > input, ' +
                    ':scope > select, :scope > textarea, :scope > [role="button"]'
                );
                
                // Only consider containers with 2+ interactive elements
                if (interactiveChildren.length < 2) return;
                
                const rect = container.getBoundingClientRect();
                const style = window.getComputedStyle(container);
                
                if (style.display === 'none' || style.visibility === 'hidden') return;
                
                const group = {
                    group_id: container.id || `group_${idx}`,
                    container_tag: container.tagName.toLowerCase(),
                    position: {
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    },
                    child_count: interactiveChildren.length,
                    children: []
                };
                
                interactiveChildren.forEach(child => {
                    const childRect = child.getBoundingClientRect();
                    group.children.push({
                        tag: child.tagName.toLowerCase(),
                        id: child.id || null,
                        text: child.innerText?.trim().substring(0, 30) || null,
                        position: {
                            x: Math.round(childRect.x),
                            y: Math.round(childRect.y)
                        }
                    });
                });
                
                groups.push(group);
            });
            
            return groups;
        }
        """
        
        groups = page.evaluate(js_code)
        return json.dumps(groups, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to detect visual groups: {e}")
        return json.dumps({"error": str(e)})


@tool()
def analyze_element_visibility(selector: str, session_id: str = "default") -> str:
    """
    Analyze if an element is truly visible to users (not just in DOM).
    Checks viewport position, opacity, z-index, etc.
    
    Args:
        selector: CSS selector for the element
        session_id: Browser session identifier
    
    Returns: JSON string with visibility analysis.
    """
    logger.debug(f"[analyze_element_visibility] selector={selector}, session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        (selector) => {
            const element = document.querySelector(selector);
            if (!element) return { error: "Element not found" };
            
            const rect = element.getBoundingClientRect();
            const style = window.getComputedStyle(element);
            
            const analysis = {
                exists: true,
                in_viewport: (
                    rect.top >= 0 &&
                    rect.left >= 0 &&
                    rect.bottom <= window.innerHeight &&
                    rect.right <= window.innerWidth
                ),
                partially_in_viewport: (
                    rect.bottom > 0 &&
                    rect.top < window.innerHeight &&
                    rect.right > 0 &&
                    rect.left < window.innerWidth
                ),
                display: style.display,
                visibility: style.visibility,
                opacity: parseFloat(style.opacity),
                z_index: style.zIndex,
                position: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                },
                is_truly_visible: (
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    parseFloat(style.opacity) > 0 &&
                    rect.width > 0 &&
                    rect.height > 0
                )
            };
            
            return analysis;
        }
        """
        
        analysis = page.evaluate(js_code, selector)
        return json.dumps(analysis, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to analyze visibility for '{selector}': {e}")
        return json.dumps({"error": str(e)})
