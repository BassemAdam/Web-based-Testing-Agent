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
        Keep it small for Phase 1; we can refine heuristics later.
        """
        assert self.page is not None

        elements: List[ElementDescriptor] = []

        # Simple heuristic: query some interactive elements
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

                    # create simple CSS locator
                    css_locator_parts = [tag]
                    if element_id:
                        css_locator_parts.append(f"#{element_id}")
                    if classes:
                        css_locator_parts.extend(f".{c}" for c in classes)
                    css_selector = "".join(css_locator_parts)

                    key = (tag, element_id, text, tuple(classes))
                    if key in seen:
                        continue
                    seen.add(key)

                    desc = ElementDescriptor(
                        id=element_id,
                        tag=tag,
                        text=text,
                        role=None,  # can be enriched later via LLM
                        aria_label=aria_label,
                        name=name_attr,
                        type=type_attr,
                        css_selector=css_selector,
                        xpath=None,  # optional future
                        attributes={},  # could add filtered attributes here
                        classes=classes,
                        bounding_box=box,
                    )
                    elements.append(desc)
                except Exception:
                    # For now, ignore elements that explode on us
                    continue

        return elements

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
