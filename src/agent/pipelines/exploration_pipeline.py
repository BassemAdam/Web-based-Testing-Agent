import time
from urllib.parse import urlparse
from typing import Optional
from ..browser.playwright_driver import BrowserDriver
from ..models.page_snapshot import PageSnapshot
from ..llm.ollama_client import LLMClient
from ..utils.keys import key_from_descriptor
import re

class ExplorationPipeline:
    def __init__(self, use_llm_summary: bool = True):
        self.llm = LLMClient() if use_llm_summary else None

    @staticmethod
    def _slug_from_url(url: str) -> str:
        parsed = urlparse(url)
        slug = (parsed.netloc + parsed.path).strip("/").replace("/", "_")
        return slug or "root"

    # def run(self, url: str) -> PageSnapshot:
    #     start_time = time.time()
    #     with BrowserDriver() as browser:
    #         browser.goto(url)

    #         title = browser.get_title()
    #         raw_html = browser.get_html()
    #         elements = browser.extract_elements()

    #         screenshot_path = browser.capture_screenshot(self._slug_from_url(url))

    #     elapsed = time.time() - start_time

    #     snapshot = PageSnapshot(
    #         url=url,
    #         title=title,
    #         raw_html=raw_html,
    #         elements=elements,
    #         screenshot_path=screenshot_path,
    #         meta={"elapsed_seconds": f"{elapsed:.3f}"},
    #     )

    #     # Optional: ask LLM for a short page summary (Phase 1 quality-of-life)
    #     if self.llm is not None:
    #         summary = self._summarize_page(snapshot)
    #         snapshot.summary = summary

    #     return snapshot
    
    def run(self, url: str) -> PageSnapshot:
        start_time = time.time()
        with BrowserDriver() as browser:
            browser.goto(url)
            snapshot = self.snapshot_current_page(browser)

        elapsed = time.time() - start_time
        snapshot.meta["elapsed_seconds"] = f"{elapsed:.3f}"
        return snapshot


    def _summarize_page(self, snapshot: PageSnapshot) -> str: 
        """
        Small prompt to get a high-level description of page & main interactive areas.
        This will be useful in Phase 2 when proposing coverage.
        """
        elements_preview = "\n".join(
            f"- {e.short_description()}" for e in snapshot.elements[:30]
        )

        prompt = f"""
You are a QA testing assistant. You are analyzing a web page (you are already give its elements, no need to browse yourself) to design test cases later.

Page title: {snapshot.title}
URL: {snapshot.url}

Here are some of the key interactive elements detected:
{elements_preview}

Give a concise summary of:
- The main purpose of the page.
- The main user flows (e.g., login, search, navigation).
- Important edge cases a tester should keep in mind.

Be concrete and concise (max 10 lines).
"""

        content = self.llm.chat(
            messages=[
                {"role": "system", "content": "You are an expert QA test planner."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            temperature=0.2,
        )
        return content

    def _slug_from_url(self,url: str) -> str:
        parsed = urlparse(url)
        slug = (parsed.netloc + parsed.path).strip("/").replace("/", "_")
        return slug or "root"

    def _extract_visible_text(self, html: str, max_chars: int = 2000) -> str:
        html = re.sub(r"<(script|style)[^>]*>.*?</\\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]

    def snapshot_current_page(self, browser: BrowserDriver) -> PageSnapshot:
        """
        Build a PageSnapshot from the browser's current page.
        Browser must already be on the target URL.
        Does NOT open or close the browser.
        """
        url = browser.current_url()
        title = browser.get_title()
        raw_html = browser.get_html()
        elements = browser.extract_elements()
        screenshot_path = browser.capture_screenshot(self._slug_from_url(url))

        elapsed = 0.0  # if you want per-snapshot timing, measure around calls above

        snapshot = PageSnapshot(
            url=url,
            title=title,
            raw_html=raw_html,
            elements=elements,
            screenshot_path=screenshot_path,
            meta={"elapsed_seconds": f"{elapsed:.3f}"},
        )

        if self.llm is not None:
            summary = self._summarize_page(snapshot)
            snapshot.summary = summary

        return snapshot