from __future__ import annotations
import json
from typing import List, Tuple, Set, Optional
from ..browser.playwright_driver import BrowserDriver
from ..models.site_graph import SiteGraph, PageNode, NavEdge
from ..models.page_snapshot import PageSnapshot
from ..llm.ollama_client import CopilotClient
from ..utils.keys import build_element_key


class AgentSiteExplorer:
    """
    AI-powered site explorer that uses an LLM agent to make intelligent
    decisions about which pages to visit and elements to interact with.
    """

    SYSTEM_PROMPT = """You are an intelligent web exploration agent. Your goal is to explore a website systematically to understand its structure and functionality.

Given information about the current page and its elements, you will decide:
1. Which links/buttons are worth clicking to discover new functionality
2. Which areas of the site are most important for testing
3. When to stop exploring a particular path

You should prioritize:
- Main navigation elements (nav bars, menus)
- Core functionality (login, signup, search, forms)
- Product/content pages
- User actions (add to cart, submit forms)

You should avoid:
- External links (different domains)
- Social media links
- Terms/Privacy policy pages (unless specifically testing those)
- Duplicate or very similar pages
- Links that look like they'll download files
"""

    def __init__(
        self,
        max_depth: int = 2,
        max_pages: int = 10,
        max_actions_per_page: int = 5,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.max_actions_per_page = max_actions_per_page
        self.llm = CopilotClient(
            model="gpt-4o",
            config={"temperature": 0.3, "max_tokens": 2000}
        )

    def _build_page_context(self, snapshot: PageSnapshot, visited_urls: Set[str]) -> str:
        """Build a context string describing the current page for the agent."""
        # Collect clickable elements
        clickable = []
        for i, e in enumerate(snapshot.elements):
            if e.tag in ["a", "button"] and e.text:
                href = e.attributes.get("href", "") if e.attributes else ""
                clickable.append({
                    "index": i,
                    "tag": e.tag,
                    "text": e.text.strip()[:100],
                    "href": href[:100] if href else None,
                    "css_selector": e.css_selector,
                })
        
        context = {
            "current_url": snapshot.url,
            "page_title": snapshot.title,
            "page_summary": snapshot.summary,
            "visited_urls": list(visited_urls)[:20],  # Limit for context
            "clickable_elements": clickable[:50],  # Limit elements
        }
        return json.dumps(context, indent=2)

    def _ask_agent_for_actions(
        self, 
        snapshot: PageSnapshot, 
        visited_urls: Set[str],
        depth: int
    ) -> List[dict]:
        """
        Ask the agent which elements to click on this page.
        Returns a list of elements to interact with.
        """
        context = self._build_page_context(snapshot, visited_urls)
        
        prompt = f"""Current exploration state:
- Current depth: {depth}/{self.max_depth}
- Pages visited: {len(visited_urls)}/{self.max_pages}

Page context:
{context}

Based on this page, select up to {self.max_actions_per_page} elements to click that would help explore the site's functionality. Prioritize elements that:
1. Lead to new, unexplored areas
2. Represent core site functionality
3. Would be important to test

Respond with a JSON array of objects, each with:
- "index": the element index from clickable_elements
- "reason": brief explanation why this element is worth exploring

Example response:
[
  {{"index": 0, "reason": "Main navigation to Products section"}},
  {{"index": 3, "reason": "Login functionality is critical to test"}}
]

If no elements are worth clicking (dead end), return an empty array: []

Respond ONLY with the JSON array, no other text."""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self.llm.chat(messages)
            # Parse JSON from response
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            actions = json.loads(response)
            return actions if isinstance(actions, list) else []
        except Exception as e:
            print(f"  [!] Agent decision failed: {e}")
            return []

    def _should_continue_exploration(
        self, 
        graph: SiteGraph, 
        visited_urls: Set[str]
    ) -> Tuple[bool, str]:
        """Ask the agent if we should continue exploring."""
        if len(graph.pages) >= self.max_pages:
            return False, "Reached max pages limit"
        
        # Could add more sophisticated agent-based decisions here
        return True, "Continue exploration"

    def explore(self, start_url: str) -> SiteGraph:
        """
        Use an AI agent to intelligently explore the site.
        """
        from ..pipelines.exploration_pipeline import ExplorationPipeline
        
        graph = SiteGraph()
        visited_urls: Set[str] = set()
        exploration = ExplorationPipeline(use_llm_summary=True)
        
        # Queue: (url, depth, from_page_id, via_key, via_reason)
        queue: List[Tuple[str, int, Optional[str], Optional[str], Optional[str]]] = [
            (start_url, 0, None, None, "Starting point")
        ]
        
        page_counter = 0

        with BrowserDriver() as browser:
            while queue and page_counter < self.max_pages:
                url, depth, from_page_id, via_key, via_reason = queue.pop(0)
                
                normalized_url = self._normalize_url(url)
                if normalized_url in visited_urls:
                    continue
                if depth > self.max_depth:
                    continue
                
                visited_urls.add(normalized_url)
                
                # Navigate and snapshot
                print(f"  [>] Agent visiting {url} (depth={depth})")
                if via_reason:
                    print(f"      Reason: {via_reason}")
                
                try:
                    browser.goto(url)
                    snapshot = exploration.snapshot_current_page(browser)
                except Exception as e:
                    print(f"  [!] Failed to load page: {e}")
                    continue
                
                # Track actual URL after redirects
                actual_url = self._normalize_url(browser.current_url())
                visited_urls.add(actual_url)
                
                # Create page node
                page_id = f"page_{page_counter}"
                page_counter += 1
                node = PageNode(id=page_id, snapshot=snapshot)
                graph.pages[page_id] = node
                
                # Connect edge if we navigated here
                if from_page_id and via_key:
                    edge = NavEdge(
                        from_page_id=from_page_id,
                        to_page_id=page_id,
                        element_key=via_key,
                        description=via_reason or f"{from_page_id} -> {page_id}",
                    )
                    graph.edges.append(edge)
                    node.incoming_edge = edge
                
                # Ask agent what to explore next
                if depth < self.max_depth:
                    print(f"  [?] Asking agent for exploration decisions...")
                    actions = self._ask_agent_for_actions(snapshot, visited_urls, depth)
                    
                    if not actions:
                        print(f"  [.] Agent found no valuable elements to explore")
                        continue
                    
                    current_page_url = browser.current_url()
                    
                    for action in actions:
                        if page_counter + len(queue) >= self.max_pages:
                            break
                        
                        idx = action.get("index")
                        reason = action.get("reason", "")
                        
                        if idx is None or idx >= len(snapshot.elements):
                            continue
                        
                        element = snapshot.elements[idx]
                        key = build_element_key(element.tag, element.text, element.id)
                        
                        print(f"  [→] Agent chose: {element.text[:50]}...")
                        print(f"      Reason: {reason}")
                        
                        # Try to click and discover new URL
                        try:
                            new_url = browser.click_element_by_key_and_get_new_url(key)
                        except Exception as e:
                            print(f"  [!] Failed to click: {e}")
                            continue
                        
                        if new_url:
                            normalized_new = self._normalize_url(new_url)
                            if normalized_new not in visited_urls:
                                queue.append((
                                    new_url, 
                                    depth + 1, 
                                    page_id, 
                                    key,
                                    reason
                                ))
                                print(f"  [+] Queued: {new_url}")
                            
                            # Go back to explore other elements
                            try:
                                browser.go_back()
                            except Exception:
                                browser.goto(current_page_url)
        
        # Final agent summary
        self._generate_exploration_summary(graph)
        
        return graph

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison."""
        url = url.rstrip("/")
        if "#" in url:
            url = url.split("#")[0]
        return url

    def _generate_exploration_summary(self, graph: SiteGraph) -> None:
        """Ask agent to summarize what was discovered."""
        pages_info = []
        for pid, node in graph.pages.items():
            pages_info.append({
                "page_id": pid,
                "url": node.snapshot.url,
                "title": node.snapshot.title,
                "summary": node.snapshot.summary,
            })
        
        prompt = f"""You explored a website and discovered {len(graph.pages)} pages:

{json.dumps(pages_info, indent=2)}

Navigation paths discovered: {len(graph.edges)}

Provide a brief summary of:
1. What type of site this is
2. Main functionality discovered
3. Areas that might need more exploration
4. Key pages for testing

Keep it concise (3-5 sentences)."""

        messages = [
            {"role": "system", "content": "You are a web testing expert summarizing site exploration results."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            summary = self.llm.chat(messages)
            print(f"\n=== Agent Exploration Summary ===")
            print(summary)
        except Exception as e:
            print(f"  [!] Failed to generate summary: {e}")