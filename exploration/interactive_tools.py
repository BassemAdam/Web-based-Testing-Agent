"""
Interactive Exploration Tools for Phase 1

These tools allow the agent to interact with the page to discover
dynamic behavior, hidden elements, and multi-step flows.
"""

from tools.decorator import tool
from browser_manager import get_page
from loguru import logger
import json
import time


@tool()
def explore_clickable_elements(session_id: str = "default") -> str:
    """
    Identify all clickable elements and their expected behavior.
    Tests what happens when each element is hovered (without actually clicking).
    
    Returns: JSON string with clickable elements and their properties.
    """
    logger.debug(f"[explore_clickable_elements] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const clickables = [];
            const selectors = [
                'button', 'a', '[role="button"]', '[onclick]',
                'input[type="submit"]', 'input[type="button"]'
            ];
            
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach((el, idx) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    
                    if (style.display === 'none' || style.visibility === 'hidden') return;
                    
                    const info = {
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        text: el.innerText?.trim() || el.value || el.getAttribute('aria-label') || null,
                        type: el.type || null,
                        href: el.href || null,
                        role: el.getAttribute('role') || null,
                        cursor: style.cursor,
                        has_onclick: el.hasAttribute('onclick'),
                        expected_action: null
                    };
                    
                    // Infer expected action
                    if (el.href) {
                        info.expected_action = el.href.startsWith('#') ? 'scroll_to_section' : 'navigate';
                    } else if (el.type === 'submit') {
                        info.expected_action = 'submit_form';
                    } else if (el.hasAttribute('data-toggle') || el.hasAttribute('data-target')) {
                        info.expected_action = 'toggle_visibility';
                    } else {
                        info.expected_action = 'trigger_interaction';
                    }
                    
                    clickables.push(info);
                });
            });
            
            return clickables;
        }
        """
        
        clickables = page.evaluate(js_code)
        return json.dumps(clickables, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to explore clickable elements: {e}")
        return json.dumps({"error": str(e)})


@tool()
def detect_dynamic_content(wait_seconds: int = 2, session_id: str = "default") -> str:
    """
    Detect content that loads dynamically after page load.
    Captures DOM before and after waiting to see what changes.
    
    Args:
        wait_seconds: How long to wait for dynamic content
        session_id: Browser session identifier
    
    Returns: JSON string with information about dynamic changes.
    """
    logger.debug(f"[detect_dynamic_content] wait_seconds={wait_seconds}, session_id={session_id}")
    page = get_page(session_id)
    
    try:
        # Capture initial state
        initial_elements = page.evaluate("""
            () => document.querySelectorAll('*').length
        """)
        
        # Wait for potential dynamic content
        page.wait_for_timeout(wait_seconds * 1000)
        
        # Capture final state
        final_elements = page.evaluate("""
            () => document.querySelectorAll('*').length
        """)
        
        # Check for AJAX indicators
        ajax_info = page.evaluate("""
            () => ({
                has_fetch: typeof window.fetch !== 'undefined',
                has_xhr: typeof XMLHttpRequest !== 'undefined',
                has_websocket: typeof WebSocket !== 'undefined',
                loading_indicators: document.querySelectorAll(
                    '[class*="loading"], [class*="spinner"], [class*="skeleton"]'
                ).length
            })
        """)
        
        result = {
            "initial_element_count": initial_elements,
            "final_element_count": final_elements,
            "elements_added": final_elements - initial_elements,
            "has_dynamic_content": final_elements > initial_elements,
            "ajax_capabilities": ajax_info,
            "wait_time_seconds": wait_seconds
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to detect dynamic content: {e}")
        return json.dumps({"error": str(e)})


@tool()
def detect_interaction_flows(session_id: str = "default") -> str:
    """
    Detect common interaction flows like login, search, checkout, etc.
    Looks for patterns in form fields and buttons.
    
    Returns: JSON string with detected flows.
    """
    logger.debug(f"[detect_interaction_flows] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const flows = [];
            
            // Detect login forms
            document.querySelectorAll('form').forEach((form, idx) => {
                const inputs = form.querySelectorAll('input');
                const inputTypes = Array.from(inputs).map(i => i.type);
                const inputNames = Array.from(inputs).map(i => i.name?.toLowerCase() || '');
                
                const hasPassword = inputTypes.includes('password');
                const hasEmail = inputTypes.includes('email') || 
                                inputNames.some(n => n.includes('email') || n.includes('user'));
                
                if (hasPassword && hasEmail) {
                    const submitBtn = form.querySelector('[type="submit"], button');
                    flows.push({
                        flow_type: 'login',
                        form_id: form.id || `form_${idx}`,
                        steps: [
                            {
                                step: 1,
                                action: 'fill_email',
                                element: Array.from(inputs).find(i => 
                                    i.type === 'email' || i.name?.toLowerCase().includes('email')
                                )?.name || null
                            },
                            {
                                step: 2,
                                action: 'fill_password',
                                element: Array.from(inputs).find(i => i.type === 'password')?.name || null
                            },
                            {
                                step: 3,
                                action: 'submit',
                                element: submitBtn?.id || submitBtn?.textContent?.trim() || 'submit_button'
                            }
                        ]
                    });
                }
                
                // Detect search forms
                const hasSearch = inputTypes.includes('search') || 
                                 inputNames.some(n => n.includes('search') || n.includes('query'));
                if (hasSearch) {
                    const searchInput = Array.from(inputs).find(i => 
                        i.type === 'search' || i.name?.toLowerCase().includes('search')
                    );
                    flows.push({
                        flow_type: 'search',
                        form_id: form.id || `form_${idx}`,
                        steps: [
                            {
                                step: 1,
                                action: 'fill_search_query',
                                element: searchInput?.name || searchInput?.id || 'search_input'
                            },
                            {
                                step: 2,
                                action: 'submit_search',
                                element: 'submit_button'
                            }
                        ]
                    });
                }
                
                // Detect registration forms
                const hasConfirmPassword = inputNames.some(n => 
                    n.includes('confirm') && n.includes('password')
                );
                if (hasPassword && hasEmail && hasConfirmPassword) {
                    flows.push({
                        flow_type: 'registration',
                        form_id: form.id || `form_${idx}`,
                        field_count: inputs.length,
                        has_terms_checkbox: !!form.querySelector('input[type="checkbox"]')
                    });
                }
            });
            
            // Detect navigation flows
            const navElements = document.querySelectorAll('nav a, [role="navigation"] a');
            if (navElements.length > 0) {
                flows.push({
                    flow_type: 'navigation',
                    link_count: navElements.length,
                    links: Array.from(navElements).slice(0, 10).map(a => ({
                        text: a.innerText?.trim(),
                        href: a.href
                    }))
                });
            }
            
            return flows;
        }
        """
        
        flows = page.evaluate(js_code)
        return json.dumps(flows, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to detect interaction flows: {e}")
        return json.dumps({"error": str(e)})


@tool()
def explore_hover_effects(session_id: str = "default") -> str:
    """
    Detect elements with hover effects (dropdowns, tooltips, etc.).
    This helps identify hidden interactive elements.
    
    Returns: JSON string with elements that have hover effects.
    """
    logger.debug(f"[explore_hover_effects] session_id={session_id}")
    page = get_page(session_id)
    
    try:
        js_code = """
        () => {
            const hoverElements = [];
            const candidates = document.querySelectorAll('button, a, [role="button"], nav *');
            
            candidates.forEach((el, idx) => {
                // Check if element has associated dropdown/tooltip
                const hasDropdown = el.getAttribute('aria-haspopup') === 'true' ||
                                   el.getAttribute('data-toggle') === 'dropdown' ||
                                   el.nextElementSibling?.classList.contains('dropdown') ||
                                   el.querySelector('[class*="dropdown"]');
                
                const hasTooltip = el.hasAttribute('title') ||
                                  el.hasAttribute('data-tooltip') ||
                                  el.getAttribute('aria-describedby');
                
                if (hasDropdown || hasTooltip) {
                    hoverElements.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        text: el.innerText?.trim().substring(0, 30) || null,
                        has_dropdown: hasDropdown,
                        has_tooltip: hasTooltip,
                        aria_haspopup: el.getAttribute('aria-haspopup'),
                        aria_expanded: el.getAttribute('aria-expanded')
                    });
                }
            });
            
            return hoverElements;
        }
        """
        
        hover_elements = page.evaluate(js_code)
        return json.dumps(hover_elements, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to explore hover effects: {e}")
        return json.dumps({"error": str(e)})


@tool()
def test_interactive_element(selector: str, action: str = "click", session_id: str = "default") -> str:
    """
    Safely test an interactive element to see what happens.
    Captures state before and after interaction.
    
    Args:
        selector: CSS selector for the element
        action: Type of action: click, hover, focus
        session_id: Browser session identifier
    
    Returns: JSON string with interaction results.
    """
    logger.debug(f"[test_interactive_element] selector={selector}, action={action}, session_id={session_id}")
    page = get_page(session_id)
    
    try:
        # Capture state before interaction
        before_url = page.url
        before_elements = page.evaluate("() => document.querySelectorAll('*').length")
        
        # Perform action
        element = page.locator(selector).first
        
        if action == "click":
            element.click()
        elif action == "hover":
            element.hover()
        elif action == "focus":
            element.focus()
        else:
            return json.dumps({"error": f"Unknown action: {action}"})
        
        # Wait a bit for any changes
        page.wait_for_timeout(500)
        
        # Capture state after interaction
        after_url = page.url
        after_elements = page.evaluate("() => document.querySelectorAll('*').length")
        
        # Check for modals or overlays
        new_modals = page.evaluate("""
            () => document.querySelectorAll('[role="dialog"], .modal, .overlay').length
        """)
        
        result = {
            "action_performed": action,
            "selector": selector,
            "url_changed": before_url != after_url,
            "new_url": after_url if before_url != after_url else None,
            "dom_changed": before_elements != after_elements,
            "elements_added": after_elements - before_elements,
            "modals_appeared": new_modals > 0,
            "success": True
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to test interactive element '{selector}': {e}")
        return json.dumps({"error": str(e), "success": False})
