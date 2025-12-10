#!/usr/bin/env python
import sys
from pathlib import Path
import json

import streamlit as st
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ---------------------------------------------------------------------
# Make `src/` importable as a package root
# ---------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent.pipelines.site_explorer import SiteExplorer
from agent.pipelines.multi_page_test_design_pipeline import MultiPageTestDesignPipeline
from agent.visualization.coverage_overlay import create_page_coverage_overlay


# ---------------------------------------------------------------------
# Helpers to cache / store state
# ---------------------------------------------------------------------
def get_designer(model_name: str | None):
    # You can extend this later to switch models via UI
    return MultiPageTestDesignPipeline(model_name=model_name)


def run_exploration(start_url: str, max_depth: int, max_pages: int, max_links: int):
    explorer = SiteExplorer(
        max_depth=max_depth,
        max_pages=max_pages,
        max_links_per_page=max_links,
    )
    graph = explorer.explore(start_url)
    return graph


def generate_overlays(graph, coverage: dict) -> dict[str, str | None]:
    overlay_dir = ROOT / "artifacts" / "coverage"
    overlay_dir.mkdir(parents=True, exist_ok=True)

    page_overlays: dict[str, str | None] = {}
    for page_id, node in graph.pages.items():
        out_img = overlay_dir / f"{page_id}_coverage.png"
        path = create_page_coverage_overlay(
            page_id=page_id,
            snapshot=node.snapshot,
            coverage=coverage,
            output_path=str(out_img),
        )
        page_overlays[page_id] = path
    return page_overlays


# ---------------------------------------------------------------------
# Streamlit App
# ---------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="Exploratory Testing Agent",
        layout="wide",
    )

    st.title("🧪 Exploratory Testing Agent – Multi-Page Planner")

    # --- Sidebar controls -------------------------------------------------
    with st.sidebar:
        st.header("Configuration")

        start_url = st.text_input(
            "Start URL",
            value="https://example.com",
            help="Seed URL for exploration",
        )

        max_depth = st.slider("Max depth", 0, 3, 1)
        max_pages = st.slider("Max pages", 1, 10, 3)
        max_links = st.slider("Max links per page", 1, 10, 3)

        model_name = st.text_input(
            "LLM model (Ollama)",
            value="deepseek-coder-v2:16b",
            help="Model passed to MultiPageTestDesignPipeline",
        )

        st.markdown("---")
        feedback_default = (
            "Add at least one negative/edge test and cover important navigation."
        )
        feedback = st.text_area(
            "Human feedback (optional)",
            value="",
            placeholder=feedback_default,
            height=100,
            help="Describe how you want the plan to change or what to focus on.",
        )

        col_run, col_refine = st.columns(2)
        run_btn = col_run.button("🚀 Explore + Generate", use_container_width=True)
        refine_btn = col_refine.button("🔁 Refine with feedback", use_container_width=True)

    # Use Streamlit session_state to persist data across reruns
    if "graph" not in st.session_state:
        st.session_state.graph = None
    if "plan" not in st.session_state:
        st.session_state.plan = None
    if "overlays" not in st.session_state:
        st.session_state.overlays = {}
    if "start_url" not in st.session_state:
        st.session_state.start_url = None

    # --- Run full pipeline ------------------------------------------------
    if run_btn:
        with st.spinner("Exploring site and generating initial test plan..."):
            graph = run_exploration(start_url, max_depth, max_pages, max_links)
            designer = get_designer(model_name or None)
            plan_dict = designer.build_plan(graph, human_feedback=None)

            # Save in session
            st.session_state.graph = graph
            st.session_state.plan = plan_dict
            st.session_state.start_url = start_url

            # Generate overlays
            overlays = generate_overlays(graph, plan_dict["coverage"])
            st.session_state.overlays = overlays

        st.success("Initial exploration + test plan ready!")

    # --- Refinement with feedback ----------------------------------------
    if refine_btn:
        if not st.session_state.graph or not st.session_state.plan:
            st.warning("Run an initial exploration first.")
        else:
            fb = feedback.strip()
            if not fb:
                st.warning("Please type some feedback before refining.")
            else:
                with st.spinner("Refining test plan using human feedback..."):
                    graph = st.session_state.graph
                    designer = get_designer(model_name or None)
                    # Rebuild plan with feedback (you can change build_plan to use prior plan if you want)
                    plan_dict = designer.build_plan(graph, human_feedback=fb)
                    st.session_state.plan = plan_dict

                    # Regenerate overlays based on new coverage
                    overlays = generate_overlays(graph, plan_dict["coverage"])
                    st.session_state.overlays = overlays

                st.success("Plan refined using your feedback!")

    # --- Show results if we have a plan ----------------------------------
    graph = st.session_state.graph
    plan = st.session_state.plan
    overlays = st.session_state.overlays
    start_url_state = st.session_state.start_url

    if graph and plan:
        st.subheader("1️⃣ Exploration Overview")

        st.write(f"**Start URL:** `{start_url_state}`")
        cols = st.columns(2)

        # Pages table
        with cols[0]:
            st.markdown("#### Pages visited")
            rows = []
            for page_id, node in graph.pages.items():
                rows.append(
                    {
                        "page_id": page_id,
                        "title": node.snapshot.title,
                        "url": node.snapshot.url,
                    }
                )
            st.table(rows)

        # Edges table
        with cols[1]:
            st.markdown("#### Navigation edges")
            if not graph.edges:
                st.write("_No navigation discovered._")
            else:
                rows = []
                for e in graph.edges:
                    rows.append(
                        {
                            "from": e.from_page_id,
                            "action": e.element_key,
                            "to": e.to_page_id,
                        }
                    )
                st.table(rows)

        st.markdown("---")
        st.subheader("2️⃣ Test Cases")

        test_cases = plan["test_cases"]
        coverage = plan["coverage"]
        coverage_summary = plan["coverage_summary"]

        # List test cases in an expander
        for tc in test_cases:
            with st.expander(f"{tc.id} – {tc.name}"):
                st.write(tc.description)
                if tc.tags:
                    st.write("**Tags:**", ", ".join(tc.tags))

                st.markdown("**Steps:**")
                for s in tc.steps:
                    st.write(
                        f"- `[ {s.page_id} ]` **{s.action}** "
                        f"target=`{s.target}` – {s.details}"
                    )

                if tc.covered_element_keys:
                    st.markdown("**Covered element keys:**")
                    for k in tc.covered_element_keys:
                        st.code(k)

        st.markdown("#### Coverage summary")
        st.write(coverage_summary or "_No coverage summary_")

        st.markdown("---")
        st.subheader("3️⃣ Visual Coverage per Page")

        for page_id, node in graph.pages.items():
            st.markdown(f"**{page_id} – {node.snapshot.title}**  \n`{node.snapshot.url}`")

            cols_page = st.columns(2)

            # Left: original screenshot
            with cols_page[0]:
                st.caption("Original screenshot")
                if node.snapshot.screenshot_path and Path(node.snapshot.screenshot_path).exists():
                    st.image(str(node.snapshot.screenshot_path))
                else:
                    st.write("_No screenshot found._")

            # Right: overlay
            with cols_page[1]:
                st.caption("Coverage overlay")
                overlay_path = overlays.get(page_id)
                if overlay_path and Path(overlay_path).exists():
                    st.image(str(overlay_path))
                else:
                    st.write("_No overlay generated for this page._")

            st.markdown("---")


if __name__ == "__main__":
    main()
