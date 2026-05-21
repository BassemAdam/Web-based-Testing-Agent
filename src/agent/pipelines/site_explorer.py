from __future__ import annotations
from typing import List, Tuple, Set
from dataclasses import dataclass
from ..browser.playwright_driver import BrowserDriver
from ..models.site_graph import SiteGraph, PageNode, NavEdge
from ..pipelines.exploration_pipeline import ExplorationPipeline
from ..utils.keys import key_from_descriptor, build_element_key

class SiteExplorer:
    """
    Explore the site starting from a seed URL, up to a limited depth/page count,
    and build a SiteGraph (pages + navigation edges).
    """

    def __init__(
        self,
        max_depth: int = 1,
        max_pages: int = 5,
        max_links_per_page: int = 3,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.max_links_per_page = max_links_per_page
        self.exploration = ExplorationPipeline(use_llm_summary=True)

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison (strip trailing slash, fragment, etc.)"""
        url = url.rstrip("/")
        # Remove fragment
        if "#" in url:
            url = url.split("#")[0]
        return url

    def _pick_navigation_elements(self, snapshot) -> List[Tuple[str, str]]:
        """
        Decide which elements on the page are worth clicking to navigate.
        Main-content links are preferred; navbar / sidebar links are explored
        last (or skipped when the page limit is reached first).
        Returns list of (element_key, human_label).
        """
        main_candidates: List[Tuple[str, str]] = []
        nav_candidates: List[Tuple[str, str]] = []

        for e in snapshot.elements:
            if e.tag == "a" and e.text:
                key = build_element_key(e.tag, e.text, e.id)
                label = e.text.strip()
                if e.is_nav_or_sidebar():
                    nav_candidates.append((key, label))
                else:
                    main_candidates.append((key, label))

        # Main content links first, nav/sidebar links appended at the end.
        combined = main_candidates + nav_candidates
        return combined[: self.max_links_per_page]

    def explore(self, start_url: str) -> SiteGraph:
        graph = SiteGraph()
        visited_urls: Set[str] = set()    # URLs we've already processed
        queued_urls: Set[str] = set()     # URLs already in queue (to avoid duplicates)
        
        # Queue: (url, depth, from_page_id, via_key)
        queue: List[Tuple[str, int, str | None, str | None]] = [
            (start_url, 0, None, None)
        ]
        queued_urls.add(self._normalize_url(start_url))
        page_counter = 0

        with BrowserDriver() as browser:
            while queue and page_counter < self.max_pages:
                url, depth, from_page_id, via_key = queue.pop(0)
                
                normalized_url = self._normalize_url(url)
                if normalized_url in visited_urls:
                    continue
                if depth > self.max_depth:
                    continue
                    
                visited_urls.add(normalized_url)

                # 1) Navigate to URL and snapshot
                print(f"  [>] Visiting {url} (depth={depth})")
                browser.goto(url)
                snapshot = self.exploration.snapshot_current_page(browser)
                
                # Also mark the actual URL as visited (may differ due to redirects)
                actual_url = self._normalize_url(browser.current_url())
                visited_urls.add(actual_url)
                queued_urls.add(actual_url)

                page_id = f"page_{page_counter}"
                page_counter += 1
                node = PageNode(id=page_id, snapshot=snapshot)
                graph.pages[page_id] = node

                # 2) Connect edge if we came via a click
                if from_page_id is not None and via_key is not None:
                    edge = NavEdge(
                        from_page_id=from_page_id,
                        to_page_id=page_id,
                        element_key=via_key,
                        description=f"{from_page_id} -> {page_id} via {via_key}",
                    )
                    graph.edges.append(edge)
                    node.incoming_edge = edge

                # 3) From this page, discover navigation links and add to queue
                if depth < self.max_depth:
                    nav_elements = self._pick_navigation_elements(snapshot)
                    current_page_url = browser.current_url()
                    
                    for key, label in nav_elements:
                        if page_counter + len(queue) >= self.max_pages:
                            # Don't queue more than we can visit
                            break
                            
                        # Try clicking the element to discover where it leads
                        try:
                            new_url = browser.click_element_by_key_and_get_new_url(key)
                        except Exception as e:
                            print(f"  [!] Failed to click {key}: {e}")
                            continue
                        
                        if new_url:
                            normalized_new = self._normalize_url(new_url)
                            
                            # Only queue if not already visited AND not already queued
                            if normalized_new not in visited_urls and normalized_new not in queued_urls:
                                queue.append((new_url, depth + 1, page_id, key))
                                queued_urls.add(normalized_new)
                                print(f"  [+] Discovered: {new_url}")
                            
                            # Go back to continue exploring other links on this page
                            try:
                                browser.go_back()
                            except Exception:
                                # If go_back fails, navigate directly
                                browser.goto(current_page_url)
                        else:
                            # Click didn't navigate - element may have other behavior
                            pass

        return graph