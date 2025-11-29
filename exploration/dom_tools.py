"""
DOM Extraction Tools for Phase 1 Exploration

These tools help the agent "see" the page through DOM analysis,
extracting structural and semantic information.
"""

from tools.decorator import tool
from browser_manager import get_page
from loguru import logger
from typing import Dict, List, Any
import json


@tool()
def extract_dom_tree(max_depth: int = 5, session_id: str = "default") -> str:
    """
    Extract a structured representation of the DOM tree with key attributes.
    Returns a JSON string representing the tree structure.
    
    Args:
        max_depth: Maximum depth to traverse (prevent overwhelming output)
        session_id: Browser session identifier
    """
    logger.debug(f"[extract_dom_tree] max_depth={max_depth}, session_id={session_id}")
    page = get_page(session_id)
    
    try:
        # JavaScript to extract DOM tree with attributes
        js_code = """
        (maxDepth) => {
            function extractNode(node, depth) {
                if (depth > maxDepth || !node || node.nodeType !== 1) return null;
                
                const result = {
                    tag: node.tagName.toLowerCase(),
                    id: node.id || null,
                    classes: Array.from(node.classList),
                    attributes: {},
                    text: null,
                    children: []
                };
                
                // Extract key attributes
                const importantAttrs = ['type', 'name', 'placeholder', 'href', 'src', 
                                       'aria-label', 'role', 'data-testid', 'value'];
                importantAttrs.forEach(attr => {
                    if (node.hasAttribute(attr)) {
                        result.attributes[attr] = node.getAttribute(attr);
                    }
                });
                
                // Get direct text (not from children)
                const directText = Array.from(node.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim())
                    .join(' ')
                    .trim();
                if (directText) result.text = directText;
                
                // Extract children
                for (let child of node.children) {
                    const childNode = extractNode(child, depth + 1);
                    if (childNode) result.children.push(childNode);
                }
                
                return result;
            }
            
            return extractNode(document.body, 0);
        }
        """
        
        dom_tree = page.evaluate(js_code, max_depth)
        return json.dumps(dom_tree, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to extract DOM tree: {e}")
        return json.dumps({"error": str(e)})


@tool()
def extract_interactive_elements(session_id: str = "default") -> str:
    """
    Find all interactive elements (buttons, inputs, links, selects, etc.)
    with their locators and attributes.
    
    Returns a JSON string with all interactive elements.
    """
    logger.debug(f"[extract_interactive_elements] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const elements = [];
            const selectors = [
                'button', 'a', 'input', 'select', 'textarea',
                '[role="button"]', '[role="link"]', '[role="textbox"]',
                '[onclick]', '[contenteditable="true"]'
            ];
            
            const processedElements = new Set();
            
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach((el, idx) => {
                    // Avoid duplicates
                    if (processedElements.has(el)) return;
                    processedElements.add(el);
                    
                    // Skip hidden elements
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || 
                        (rect.width === 0 && rect.height === 0)) {
                        return;
                    }
                    
                    const element = {
                        type: el.tagName.toLowerCase(),
                        locators: {},
                        attributes: {},
                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        visible_text: el.innerText?.trim().substring(0, 100) || null,
                        is_visible: true
                    };
                    
                    // Generate multiple locator strategies
                    if (el.id) element.locators.id = `#${el.id}`;
                    
                    if (el.name) element.locators.name = `[name="${el.name}"]`;
                    
                    const dataTestId = el.getAttribute('data-testid');
                    if (dataTestId) element.locators.testid = `[data-testid="${dataTestId}"]`;
                    
                    const ariaLabel = el.getAttribute('aria-label');
                    if (ariaLabel) element.locators.aria = `[aria-label="${ariaLabel}"]`;
                    
                    if (el.innerText?.trim()) {
                        element.locators.text = el.innerText.trim().substring(0, 50);
                    }
                    
                    // Generate CSS selector path
                    const cssPath = [];
                    let current = el;
                    while (current && current !== document.body) {
                        let selector = current.tagName.toLowerCase();
                        if (current.id) {
                            selector += `#${current.id}`;
                            cssPath.unshift(selector);
                            break;
                        }
                        if (current.className) {
                            const classes = Array.from(current.classList).join('.');
                            if (classes) selector += `.${classes}`;
                        }
                        cssPath.unshift(selector);
                        current = current.parentElement;
                    }
                    element.locators.css = cssPath.join(' > ');
                    
                    // Capture important attributes
                    ['type', 'placeholder', 'value', 'href', 'role', 'disabled', 
                     'checked', 'required'].forEach(attr => {
                        if (el.hasAttribute(attr)) {
                            element.attributes[attr] = el.getAttribute(attr);
                        }
                    });
                    
                    elements.push(element);
                });
            });
            
            return elements;
        }
        """
        
        elements = page.evaluate(js_code)
        return json.dumps(elements, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to extract interactive elements: {e}")
        return json.dumps({"error": str(e)})


@tool()
def extract_accessibility_tree(session_id: str = "default") -> str:
    """
    Extract the accessibility tree which provides semantic information
    about page structure and roles.
    
    Returns a JSON representation of the accessibility tree.
    """
    logger.debug(f"[extract_accessibility_tree] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        # Get accessibility snapshot
        # Note: This is a Playwright CDP feature
        snapshot = page.accessibility.snapshot()
        return json.dumps(snapshot, indent=2) if snapshot else json.dumps({"message": "No accessibility tree available"})
    
    except Exception as e:
        logger.error(f"Failed to extract accessibility tree: {e}")
        return json.dumps({"error": str(e)})


@tool()
def detect_page_sections(session_id: str = "default") -> str:
    """
    Detect logical page sections (header, nav, main, footer, forms, etc.)
    using semantic HTML tags and heuristics.
    
    Returns a JSON string with identified sections.
    """
    logger.debug(f"[detect_page_sections] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const sections = [];
            
            // Semantic HTML5 sections
            const semanticTags = ['header', 'nav', 'main', 'article', 'section', 
                                 'aside', 'footer', 'form'];
            
            semanticTags.forEach(tag => {
                document.querySelectorAll(tag).forEach((el, idx) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    
                    // Skip invisible sections
                    if (style.display === 'none' || style.visibility === 'hidden') {
                        return;
                    }
                    
                    const section = {
                        type: tag,
                        id: el.id || `${tag}_${idx}`,
                        classes: Array.from(el.classList),
                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        role: el.getAttribute('role') || tag,
                        aria_label: el.getAttribute('aria-label') || null,
                        // Count interactive elements inside
                        interactive_count: el.querySelectorAll(
                            'button, a, input, select, textarea, [role="button"]'
                        ).length
                    };
                    
                    sections.push(section);
                });
            });
            
            // Detect forms specifically
            document.querySelectorAll('form').forEach((form, idx) => {
                const fields = [];
                form.querySelectorAll('input, select, textarea').forEach(field => {
                    fields.push({
                        type: field.tagName.toLowerCase(),
                        input_type: field.type || null,
                        name: field.name || null,
                        id: field.id || null,
                        required: field.required || false,
                        placeholder: field.placeholder || null
                    });
                });
                
                const submitBtn = form.querySelector('[type="submit"], button[type="submit"]');
                
                sections.push({
                    type: 'form',
                    id: form.id || `form_${idx}`,
                    action: form.action || null,
                    method: form.method || 'get',
                    fields: fields,
                    has_submit_button: !!submitBtn
                });
            });
            
            return sections;
        }
        """
        
        sections = page.evaluate(js_code)
        return json.dumps(sections, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to detect page sections: {e}")
        return json.dumps({"error": str(e)})


@tool()
def detect_technologies(session_id: str = "default") -> str:
    """
    Detect frontend frameworks and libraries in use on the page.
    (React, Vue, Angular, jQuery, etc.)
    
    Returns a JSON string with detected technologies.
    """
    logger.debug(f"[detect_technologies] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const technologies = [];
            
            // Check for common frameworks
            if (window.React || document.querySelector('[data-reactroot], [data-reactid]')) {
                technologies.push('React');
            }
            if (window.Vue || document.querySelector('[data-v-]')) {
                technologies.push('Vue');
            }
            if (window.angular || document.querySelector('[ng-app], [data-ng-app]')) {
                technologies.push('Angular');
            }
            if (window.jQuery || window.$) {
                technologies.push('jQuery');
            }
            if (document.querySelector('[data-svelte]')) {
                technologies.push('Svelte');
            }
            if (window.Ember) {
                technologies.push('Ember');
            }
            
            // Check for common UI libraries
            if (document.querySelector('[class*="mui"], [class*="MuiButton"]')) {
                technologies.push('Material-UI');
            }
            if (document.querySelector('[class*="ant-"]')) {
                technologies.push('Ant Design');
            }
            if (document.querySelector('[class*="bootstrap"]')) {
                technologies.push('Bootstrap');
            }
            
            return technologies;
        }
        """
        
        technologies = page.evaluate(js_code)
        return json.dumps(technologies, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to detect technologies: {e}")
        return json.dumps({"error": str(e)})
