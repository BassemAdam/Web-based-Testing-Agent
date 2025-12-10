from agent.pipelines.site_explorer import SiteExplorer

explorer = SiteExplorer(max_depth=1, max_pages=3, max_links_per_page=2)
graph = explorer.explore("https://www.youtube.com")

print("Pages visited:")
for pid, node in graph.pages.items():
    print(pid, "->", node.snapshot.url)

print("Edges:")
for e in graph.edges:
    print(e.from_page_id, "--", e.element_key, "-->", e.to_page_id)
