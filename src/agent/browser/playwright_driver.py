from __future__ import annotations
from pathlib import Path
from typing import List, Optional
from playwright.sync_api import sync_playwright, Page
from ..config import browser_config, exploration_config
from ..models.element_descriptor import ElementDescriptor
from ..utils.keys import key_from_descriptor

class BrowserDriver:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self.page: Optional[Page] = None

    def __enter__(self) -> "BrowserDriver":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=browser_config.headless,
        )
        self._context = self._browser.new_context()
        self.page = self._context.new_page()
        self.page.set_default_timeout(browser_config.default_timeout_ms)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def goto(self, url: str, wait_until: str = "load", timeout_ms: Optional[int] = None):
        assert self.page is not None, "BrowserDriver not initialized"
        timeout = timeout_ms or browser_config.navigation_timeout_ms
        self.page.goto(url, timeout=timeout, wait_until=wait_until)

    def capture_screenshot(self, url_slug: str) -> Optional[str]:
        if not exploration_config.capture_screenshot or self.page is None:
            return None

        out_dir = Path(exploration_config.screenshot_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{url_slug}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return str(path)

    def extract_elements(self, max_elements: int = 200) -> List[ElementDescriptor]:
        """
        Extract candidate elements (buttons, inputs, links) with their locators.
        """
        assert self.page is not None

        elements: List[ElementDescriptor] = []
        selector_groups = [
            "a",
            "button",
            "input",          # All input types
            "select",
            "textarea",
            "[role=button]",
            "[role=link]",
        ]

        seen = set()

        for selector in selector_groups:
            for handle in self.page.query_selector_all(selector):
                if len(elements) >= max_elements:
                    break

                try:
                    box = handle.bounding_box()
                    tag = handle.evaluate("e => e.tagName.toLowerCase()")
                    text = handle.inner_text().strip()[:200] if tag not in ["input", "select", "textarea"] else ""
                    element_id = handle.get_attribute("id") or ""
                    classes = (handle.get_attribute("class") or "").split()
                    aria_label = handle.get_attribute("aria-label")
                    name_attr = handle.get_attribute("name")
                    type_attr = handle.get_attribute("type")
                    href = handle.get_attribute("href") if tag == "a" else None
                    placeholder = handle.get_attribute("placeholder")
                    
                    # Get testing-specific attributes
                    data_testid = (
                        handle.get_attribute("data-testid") or
                        handle.get_attribute("data-test") or
                        handle.get_attribute("data-cy") or
                        handle.get_attribute("data-test-id")
                    )
                    
                    # Build attributes dict
                    attributes = {}
                    if href:
                        attributes["href"] = href
                    if placeholder:
                        attributes["placeholder"] = placeholder
                    if data_testid:
                        attributes["data-testid"] = data_testid
                    
                    # Build unique key - INCLUDE name and type for inputs
                    from ..utils.keys import build_element_key
                    element_key = build_element_key(
                        tag=tag,
                        text=text,
                        id=element_id,
                        name=name_attr,
                        input_type=type_attr
                    )
                    
                    # Use element_key for deduplication (not just tag/id/text/classes)
                    if element_key in seen:
                        continue
                    seen.add(element_key)
                    
                    # Build CSS selector
                    css_selector = self._build_specific_selector(
                        handle, tag, element_id, classes, text, 
                        aria_label, name_attr, type_attr, href, 
                        placeholder, data_testid
                    )

                    desc = ElementDescriptor(
                        id=element_id,
                        tag=tag,
                        text=text,
                        role=None,
                        aria_label=aria_label,
                        name=name_attr,
                        type=type_attr,
                        css_selector=css_selector,
                        xpath=self._build_xpath(handle, tag, text, element_id, name_attr),
                        attributes=attributes,
                        classes=classes,
                        bounding_box=box,
                    )
                    elements.append(desc)

                except Exception:
                    continue

        return elements

    def _build_specific_selector(
        self, 
        handle, 
        tag: str, 
        element_id: str, 
        classes: List[str], 
        text: str,
        aria_label: str,
        name_attr: str,
        type_attr: str,
        href: str,
        placeholder: str,
        data_testid: str
    ) -> str:
        """
        Build a specific, unique CSS selector for an element.
        Priority: data-testid > ID > name > aria-label > placeholder > type > href > text > nth-child
        """
        # 1. data-testid (best for testing)
        if data_testid:
            return f'[data-testid="{data_testid}"]'
        
        # 2. ID (if not auto-generated)
        if element_id and not self._is_generated_id(element_id):
            return f"#{element_id}"
        
        # 3. name attribute for form elements
        if name_attr and tag in ["input", "select", "textarea"]:
            return f'{tag}[name="{name_attr}"]'
        
        # 4. aria-label
        if aria_label:
            return f'{tag}[aria-label="{aria_label}"]'
        
        # 5. placeholder for inputs
        if placeholder and tag == "input":
            return f'input[placeholder="{placeholder}"]'
        
        # 6. type attribute for inputs (email, password, etc.)
        if type_attr and tag == "input" and type_attr in ["email", "password", "search", "tel", "url"]:
            return f'input[type="{type_attr}"]'
        
        # 7. href for links
        if tag == "a" and href and not href.startswith(("#", "javascript:")):
            if len(href) < 80:
                return f'a[href="{href}"]'
        
        # 8. Text-based selector for buttons/links
        if text and len(text) < 50 and tag in ["a", "button"]:
            clean_text = text.replace('"', '\\"').replace('\n', ' ').strip()[:30]
            if clean_text:
                return f'{tag}:has-text("{clean_text}")'
        
        # 9. Specific classes
        specific_classes = self._get_specific_classes(classes)
        if specific_classes:
            return f"{tag}.{'.'.join(specific_classes[:2])}"
        
        # 10. Fallback: nth-child with parent context
        try:
            nth_info = handle.evaluate("""e => {
                const parent = e.parentElement;
                if (!parent) return null;
                const siblings = Array.from(parent.children).filter(
                    c => c.tagName === e.tagName
                );
                const index = siblings.indexOf(e) + 1;
                const parentTag = parent.tagName.toLowerCase();
                const parentClass = parent.className.split(' ')[0] || '';
                return { index, parentTag, parentClass };
            }""")
            
            if nth_info:
                parent_selector = nth_info["parentTag"]
                if nth_info["parentClass"]:
                    parent_selector += f".{nth_info['parentClass']}"
                return f"{parent_selector} > {tag}:nth-child({nth_info['index']})"
        except Exception:
            pass
        
        # Last resort
        return tag

    def _is_generated_id(self, id_value: str) -> bool:
        """Check if an ID looks auto-generated."""
        import re
        if not id_value:
            return True
        
        patterns = [
            r'^[a-f0-9]{8,}$',
            r'^\d+$',
            r'^:r\d+:$',
            r'^ember\d+$',
            r'^react-',
        ]
        return any(re.match(p, id_value, re.IGNORECASE) for p in patterns)

    def _get_specific_classes(self, classes: List[str]) -> List[str]:
        """Filter to keep only specific, meaningful classes."""
        generic = {
            "btn", "button", "link", "input", "form-control", "form-group",
            "container", "wrapper", "row", "col", "flex", "grid", "block",
            "active", "disabled", "hidden", "show", "fade",
            "nav", "navbar", "dropdown", "modal", "card",
        }
        
        specific = []
        for cls in classes:
            if cls.lower() in generic:
                continue
            if len(cls) < 3:
                continue
            # Prefer semantic classes with dashes/underscores
            if "-" in cls or "_" in cls:
                specific.insert(0, cls)
            else:
                specific.append(cls)
        
        return specific[:2]

    def _build_xpath(
        self, handle, tag: str, text: str, element_id: str, name_attr: str
    ) -> str:
        """Build an XPath selector as fallback."""
        if element_id:
            return f'//{tag}[@id="{element_id}"]'
        if name_attr:
            return f'//{tag}[@name="{name_attr}"]'
        if text and len(text) < 50:
            clean = text.replace("'", "\\'").replace('\n', ' ').strip()[:30]
            return f"//{tag}[contains(text(), '{clean}')]"
        return f"//{tag}"

    def get_html(self) -> str:
        assert self.page is not None
        return self.page.content()

    def get_title(self) -> str:
        assert self.page is not None
        return self.page.title()
    
    def current_url(self) -> str:
        assert self.page is not None
        return self.page.url

    def click_element(self, element) -> None:
        """
        element is a Playwright element handle (NOT ElementDescriptor).
        Simple wrapper; we'll use it internally.
        """
        element.click()

    def find_element_by_key(self, key: str):
        """
        Given an element key (tag|text|id), find a matching element handle.
        Very simple heuristic for navigation clicks.
        """
        assert self.page is not None
        tag, text, el_id = key.split("|", 2)
        candidates = self.page.query_selector_all(tag)

        for handle in candidates:
            h_id = handle.get_attribute("id") or ""
            inner = (handle.inner_text() or "").strip()
            h_key = f"{tag}|{inner}|{h_id}"
            if h_key == key:
                return handle
        return None

    def click_element_by_key_and_get_new_url(self, key: str, wait_for: str = "load") -> str | None:
        """
        Click an element identified by our element key and return the new URL
        (if navigation happened). Returns None if no navigation occurred.
        """
        assert self.page is not None
        before = self.page.url
        handle = self.find_element_by_key(key)
        if handle is None:
            return None

        try:
            with self.page.expect_navigation(wait_until=wait_for, timeout=5000) as nav:
                handle.click()
            # Navigation happened
            if nav.value is not None:
                return nav.value.url
            # nav.value is None means no navigation
            return None
        except Exception:
            # No navigation occurred (timeout or other error)
            # Check if URL changed anyway (e.g., hash change)
            after = self.page.url
            if after != before:
                return after
            return None

    def go_back(self, wait_for: str = "load") -> None:
        assert self.page is not None
        self.page.go_back(wait_until=wait_for, timeout=15000)
