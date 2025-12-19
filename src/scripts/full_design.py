#!/usr/bin/env python
import sys
import json
import time
from pathlib import Path
from dataclasses import asdict

# ---------------------------------------------------------------------
# Make `src/` importable as a package root (when running from project root)
# ---------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent.parent  # Go up to project root
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ---------------------------------------------------------------------
# Imports from your agent code
# ---------------------------------------------------------------------
from agent.pipelines.site_explorer import SiteExplorer
from agent.pipelines.agent_explorer import AgentSiteExplorer  # New import
from agent.pipelines.multi_page_test_design_pipeline import MultiPageTestDesignPipeline
from agent.visualization.coverage_overlay import create_page_coverage_overlay


def main() -> None:
    start_time = time.time()
    
    # -----------------------------------------------------------------
    # 1) CLI args
    # -----------------------------------------------------------------
    import argparse

    parser = argparse.ArgumentParser(
        description="Run multi-page exploration + test design + coverage overlay."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://www.youtube.com",
        help="Start URL to explore (default: https://www.youtube.com)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=1,
        help="Maximum navigation depth from the start page (default: 1)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Maximum number of pages to visit (default: 3)",
    )
    parser.add_argument(
        "--max-links-per-page",
        type=int,
        default=3,
        help="Maximum number of links to click per page (default: 3)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override LLM model name for test design (e.g., gpt-4o).",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="artifacts",
        help="Directory to save output files (default: artifacts)",
    )
    parser.add_argument(
        "--use-agent",
        action="store_true",
        help="Use AI agent for intelligent exploration instead of rule-based (default: False)",
    )

    args = parser.parse_args()

    start_url = args.url
    exploration_mode = "Agent-based" if args.use_agent else "Rule-based"
    
    print(f"[+] Starting multi-page exploration at: {start_url}")
    print(f"    Mode: {exploration_mode}")
    print(
        f"    max_depth={args.max_depth}, "
        f"max_pages={args.max_pages}, "
        f"max_links_per_page={args.max_links_per_page}"
    )

    # -----------------------------------------------------------------
    # 2) Phase 1 – explore & build SiteGraph
    # -----------------------------------------------------------------
    if args.use_agent:
        print("\n[+] Using AI agent for intelligent exploration...")
        explorer = AgentSiteExplorer(
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            max_actions_per_page=args.max_links_per_page,
        )
    else:
        print("\n[+] Using rule-based exploration...")
        explorer = SiteExplorer(
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            max_links_per_page=args.max_links_per_page,
        )
    
    graph = explorer.explore(start_url)

    print("\n=== Pages visited ===")
    for page_id, node in graph.pages.items():
        print(f"{page_id} -> {node.snapshot.url}")

    print("\n=== Navigation edges ===")
    if not graph.edges:
        print("(no edges / navigation discovered)")
    else:
        for edge in graph.edges:
            print(f"{edge.from_page_id} -- {edge.element_key} --> {edge.to_page_id}")

    # -----------------------------------------------------------------
    # 3) Phase 2 – generate multi-page test plan
    # -----------------------------------------------------------------
    print("\n[+] Generating multi-page test plan from site graph...")
    designer = MultiPageTestDesignPipeline(model_name=args.model)
    if args.use_agent:
        plan_dict = designer.build_plan_from_paths(graph, start_url=start_url)
    else:
        plan_dict = designer.build_plan(graph, human_feedback=None)

    test_cases = plan_dict["test_cases"]
    coverage = plan_dict["coverage"]
    coverage_summary = plan_dict["coverage_summary"]

    print("\n=== Multi-page test cases ===")
    if not test_cases:
        print("(no test cases returned by the LLM)")
    else:
        for tc in test_cases:
            print(f"• {tc.id} - {tc.name}")
            print(f"  {tc.description}")
            if tc.tags:
                print(f"  tags: {', '.join(tc.tags)}")
            for step in tc.steps:
                print(
                    f"    - [{step.page_id}] {step.action}"
                    f"  target={step.target!r}"
                    f"  details={step.details!r}"
                )
            print()

    print("\n=== Coverage (per page::element_key) ===")
    if not coverage:
        print("(no coverage information)")
    else:
        for k, tcs in coverage.items():
            print(f"{k} => {tcs}")

    print("\n=== Coverage summary ===")
    print(coverage_summary or "(no coverage summary)")

    # -----------------------------------------------------------------
    # 4) Phase 3 – generate per-page coverage overlays
    # -----------------------------------------------------------------
    print("\n[+] Generating coverage overlays per page...")
    out_dir = Path(args.out_dir)
    overlay_dir = out_dir / "coverage"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    page_overlays: dict[str, str] = {}
    for page_id, node in graph.pages.items():
        try:
            out_img = overlay_dir / f"{page_id}_coverage.png"
            result_path = create_page_coverage_overlay(
                page_id=page_id,
                snapshot=node.snapshot,
                coverage=coverage,
                output_path=str(out_img),
            )
            page_overlays[page_id] = result_path
            print(f"  {page_id}: overlay saved to {result_path}")
        except FileNotFoundError as e:
            print(f"  {page_id}: skipping overlay – {e}")

    # -----------------------------------------------------------------
    # 5) Save JSON artifacts
    # -----------------------------------------------------------------
    elapsed = time.time() - start_time

    # Helper: serialize snapshot
    def serialize_snapshot(snapshot):
        return {
            "url": snapshot.url,
            "title": snapshot.title,
            "raw_html": snapshot.raw_html,
            "elements": [asdict(e) for e in snapshot.elements],
            "screenshot_path": snapshot.screenshot_path,
            "summary": snapshot.summary,
            "meta": snapshot.meta or {},
        }

    # -----------------------------------------------------------------
    # 5a) Save SNAPSHOT SELECTORS file
    # -----------------------------------------------------------------
    snapshots_dir = out_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    # Build pages dict with full snapshot data
    pages_data = {}
    for pid, node in graph.pages.items():
        pages_data[pid] = {
            "snapshot": serialize_snapshot(node.snapshot),
            "coverage_overlay_path": page_overlays.get(pid),
        }

    snapshot_data = {
        "start_url": start_url,
        "pages": pages_data,
        "edges": [
            {
                "from_page_id": e.from_page_id,
                "to_page_id": e.to_page_id,
                "element_key": e.element_key,
                "description": e.description,
            }
            for e in graph.edges
        ],
        "meta": {
            "elapsed_seconds": f"{elapsed:.3f}",
            "max_depth": args.max_depth,
            "max_pages": args.max_pages,
            "max_links_per_page": args.max_links_per_page,
            "exploration_mode": exploration_mode,
        },
    }

    snapshot_path = snapshots_dir / "site_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot_data, indent=2), encoding="utf-8")
    print(f"\n[+] Site snapshot saved to: {snapshot_path}")

    # -----------------------------------------------------------------
    # 5b) Save TEST CASES file
    # -----------------------------------------------------------------
    test_plans_dir = out_dir / "test_plans"
    test_plans_dir.mkdir(parents=True, exist_ok=True)

    # Serialize TestCase dataclasses to dict
    serializable_tcs = []
    for tc in test_cases:
        tc_dict = {
            "id": tc.id,
            "name": tc.name,
            "description": tc.description,
            "tags": tc.tags,
            "steps": [
                {
                    "action": s.action,
                    "page_id": s.page_id,
                    "target": s.target,
                    "details": s.details,
                }
                for s in tc.steps
            ],
            "covered_element_keys": tc.covered_element_keys,
            "selectors": [
                {
                    "element_key": sel.element_key,
                    "page_id": sel.page_id,
                    "css_selector": sel.css_selector,
                    "xpath": sel.xpath,
                    "description": sel.description,
                }
                for sel in tc.selectors
            ],
            "meta": tc.meta,
        }
        serializable_tcs.append(tc_dict)

    # Build pages object for the test plan
    pages_info = {}
    for pid, node in graph.pages.items():
        pages_info[pid] = {
            "url": node.snapshot.url,
            "title": node.snapshot.title,
            "summary": node.snapshot.summary,
            "screenshot_path": node.snapshot.screenshot_path,
            "element_count": len(node.snapshot.elements),
        }

    # Build edges info for the test plan
    edges_info = [
        {
            "from_page_id": e.from_page_id,
            "to_page_id": e.to_page_id,
            "element_key": e.element_key,
            "description": e.description,
        }
        for e in graph.edges
    ]

    test_plan_data = {
        "start_url": start_url,
        "snapshot_file": str(snapshot_path),
        "pages": pages_info,
        "edges": edges_info,
        "test_cases": serializable_tcs,
        "element_coverage": coverage,
        "coverage_summary": coverage_summary,
        "meta": {
            "elapsed_seconds": f"{elapsed:.3f}",
            "max_depth": args.max_depth,
            "max_pages": args.max_pages,
            "max_links_per_page": args.max_links_per_page,
            "exploration_mode": exploration_mode,
        },
    }

    test_plan_path = test_plans_dir / "test_plan.json"
    test_plan_path.write_text(json.dumps(test_plan_data, indent=2), encoding="utf-8")
    print(f"[+] Test plan saved to: {test_plan_path}")

    # -----------------------------------------------------------------
    # 6) Final summary
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("EXPLORATION COMPLETE")
    print("=" * 60)
    print(f"  Mode:        {exploration_mode}")
    print(f"  Pages:       {len(graph.pages)}")
    print(f"  Edges:       {len(graph.edges)}")
    print(f"  Test Cases:  {len(test_cases)}")
    print(f"  Time:        {elapsed:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
