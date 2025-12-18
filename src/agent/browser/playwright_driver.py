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

    def goto(self, url: str):
        assert self.page is not None, "BrowserDriver not initialized"
        self.page.goto(url, timeout=browser_config.navigation_timeout_ms)

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
            "input",
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
                    text = handle.inner_text().strip()[:200] if tag != "input" else ""
                    element_id = handle.get_attribute("id") or ""
                    classes = (handle.get_attribute("class") or "").split()
                    aria_label = handle.get_attribute("aria-label")
                    name_attr = handle.get_attribute("name")
                    type_attr = handle.get_attribute("type")
                    href = handle.get_attribute("href") if tag == "a" else None
                    
                    # Build a more specific CSS selector
                    css_selector = self._build_specific_selector(
                        handle, tag, element_id, classes, text, aria_label, href
                    )

                    key = (tag, element_id, text, tuple(classes))
                    if key in seen:
                        continue
                    seen.add(key)

                    desc = ElementDescriptor(
                        id=element_id,
                        tag=tag,
                        text=text,
                        role=None,
                        aria_label=aria_label,
                        name=name_attr,
                        type=type_attr,
                        css_selector=css_selector,
                        xpath=self._build_xpath(handle, tag, text, element_id),
                        attributes={"href": href} if href else {},
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
        href: str
    ) -> str:
        """
        Build a specific, unique CSS selector for an element.
        Priority: ID > data-testid > aria-label > href > text-based > nth-child
        """
        # 1. ID is most reliable
        if element_id:
            return f"{tag}#{element_id}"
        
        # 2. Check for data-testid
        data_testid = handle.get_attribute("data-testid")
        if data_testid:
            return f'{tag}[data-testid="{data_testid}"]'
        
        # 3. Check for data-test or data-cy (common testing attributes)
        for attr in ["data-test", "data-cy", "data-automation"]:
            value = handle.get_attribute(attr)
            if value:
                return f'{tag}[{attr}="{value}"]'
        
        # 4. Aria-label for accessibility
        if aria_label:
            return f'{tag}[aria-label="{aria_label}"]'
        
        # 5. For links, use href if it's specific enough
        if tag == "a" and href and not href.startswith("#") and href != "/":
            # Use partial href match for cleaner selectors
            if len(href) < 100:
                return f'{tag}[href="{href}"]'
        
        # 6. Specific classes (filter out generic utility classes)
        specific_classes = [c for c in classes if not self._is_generic_class(c)]
        if specific_classes:
            class_selector = "".join(f".{c}" for c in specific_classes[:3])
            return f"{tag}{class_selector}"
        
        # 7. For buttons/links with text, use :has-text or combine with parent
        if text and len(text) < 50:
            clean_text = text.replace('"', '\\"').replace('\n', ' ').strip()
            if clean_text:
                # Try to get a unique selector using text
                return f'{tag}:has-text("{clean_text[:30]}")'
        
        # 8. Fallback: try to get nth-child position
        try:
            nth = handle.evaluate("""e => {
                const siblings = Array.from(e.parentElement.children).filter(
                    c => c.tagName === e.tagName
                );
                return siblings.indexOf(e) + 1;
            }""")
            parent_tag = handle.evaluate("e => e.parentElement?.tagName?.toLowerCase() || ''")
            if parent_tag and nth:
                return f"{parent_tag} > {tag}:nth-child({nth})"
        except Exception:
            pass
        
        # 9. Last resort with all classes
        if classes:
            return f"{tag}.{'.'.join(classes[:2])}"
        
        return tag

    def _is_generic_class(self, class_name: str) -> bool:
        """Check if a class name is too generic to be useful for selection."""
        generic_patterns = [
            "btn", "button", "link", "nav", "menu", "item", "list",
            "container", "wrapper", "row", "col", "flex", "grid",
            "text", "icon", "img", "active", "disabled", "hidden",
            "show", "fade", "in", "out", "left", "right", "center"
        ]
        lower = class_name.lower()
        # Keep class if it has specific naming (e.g., "products-link", "cart-button")
        if "-" in class_name or "_" in class_name:
            return False
        return lower in generic_patterns or len(lower) < 3

    def _build_xpath(self, handle, tag: str, text: str, element_id: str) -> str:
        """Build an XPath selector as fallback."""
        if element_id:
            return f'//{tag}[@id="{element_id}"]'
        if text and len(text) < 50:
            clean_text = text.replace("'", "\\'").replace('\n', ' ').strip()[:30]
            return f'//{tag}[contains(text(), "{clean_text}")]'
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
