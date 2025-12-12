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
from test_runner import TestRunner


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


# Initialize test runner
test_runner = TestRunner(ROOT)


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
        
        st.markdown("---")
        st.subheader("Test Execution")
        
        test_gen_feedback = st.text_area(
            "Test Generation Feedback (optional)",
            value="",
            placeholder="E.g., Use specific assertions for login, handle dynamic popups...",
            height=100,
            help="Provide instructions to the code generator to refine the test code."
        )
        
        col_gen, col_run = st.columns(2)
        generate_tests_btn = col_gen.button("🔧 Generate Tests", use_container_width=True)
        run_tests_btn = col_run.button("▶️ Run Tests", use_container_width=True, type="primary")

    # Use Streamlit session_state to persist data across reruns
    if "graph" not in st.session_state:
        st.session_state.graph = None
    if "plan" not in st.session_state:
        st.session_state.plan = None
    if "overlays" not in st.session_state:
        st.session_state.overlays = {}
    if "start_url" not in st.session_state:
        st.session_state.start_url = None
    if "test_results" not in st.session_state:
        st.session_state.test_results = None
    if "tests_generated" not in st.session_state:
        st.session_state.tests_generated = False
    if "show_exploration" not in st.session_state:
        st.session_state.show_exploration = True

    # --- Run full pipeline ------------------------------------------------
    if run_btn:
        with st.spinner("Exploring site and generating initial test plan..."):
            graph = run_exploration(start_url, max_depth, max_pages, max_links)
            designer = get_designer(model_name or None)
            plan_dict = designer.build_plan(graph, human_feedback=None)
            
            # Add start_url to plan for code generation
            plan_dict["start_url"] = start_url

            # Save in session
            st.session_state.graph = graph
            st.session_state.plan = plan_dict
            st.session_state.start_url = start_url
            st.session_state.show_exploration = True

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
                    
                    # Preserve start_url in refined plan
                    plan_dict["start_url"] = st.session_state.start_url
                    st.session_state.plan = plan_dict

                    # Regenerate overlays based on new coverage
                    overlays = generate_overlays(graph, plan_dict["coverage"])
                    st.session_state.overlays = overlays

                st.success("Plan refined using your feedback!")
    
    # --- Generate Tests ---------------------------------------------------
    if generate_tests_btn:
        plan_path = None
        
        # Priority: Check disk first, then session
        possible_plan = ROOT / "src" / "artifacts" / "test_plans" / "test_plan.json"
        if possible_plan.exists():
            plan_path = str(possible_plan)
            st.info("Using existing test plan from disk.")
        elif st.session_state.plan:
            plan_path = test_runner.save_plan(st.session_state.plan)
        else:
            st.warning("Please generate a test plan first.")
        
        if plan_path:
            with st.spinner("Generating test code..."):
                # Pass the feedback from the sidebar
                success = test_runner.generate_tests(plan_path, feedback=test_gen_feedback)
                
                if success:
                    st.session_state.tests_generated = True
                    st.success("✅ Test code generated successfully!")
                else:
                    st.error("❌ Failed to generate test code.")
    
    # --- Run Tests --------------------------------------------------------
    if run_tests_btn:
        tests_dir = ROOT / "artifacts" / "generated_tests" / "tests"
        if not tests_dir.exists() or not list(tests_dir.glob("test_*.py")):
            st.warning("Please generate tests first using the '🔧 Generate Tests' button.")
        else:
            with st.spinner("Running tests..."):
                test_execution_result = test_runner.run_tests()
                st.session_state.test_results = test_execution_result
                
                # Clear exploration state to show only test results
                st.session_state.show_exploration = False
            
            # Show success or failure based on return code and results
            if test_execution_result["return_code"] == -1:
                st.error(f"❌ Error running tests: {test_execution_result['stderr']}")
            elif test_execution_result["success"]:
                st.success(f"✅ All tests passed! ({len(test_execution_result['results'])} tests)")
            else:
                st.error(f"❌ Some tests failed. See results below. ({len(test_execution_result['results'])} tests run)")

    # --- Show results if we have a plan ----------------------------------
    graph = st.session_state.graph
    plan = st.session_state.plan
    overlays = st.session_state.overlays
    start_url_state = st.session_state.start_url
    test_results = st.session_state.test_results
    show_exploration = st.session_state.show_exploration

    # Show test results if available
    if test_results:
        st.markdown("---")
        st.header("🧪 Test Execution Results")
        
        if test_results["results"]:
            # Create summary metrics
            total_tests = len(test_results["results"])
            passed_tests = sum(1 for r in test_results["results"] if r["status"] == "PASSED")
            failed_tests = total_tests - passed_tests
            pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
            
            # Summary row
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Tests", total_tests)
            col2.metric("✅ Passed", passed_tests)
            col3.metric("❌ Failed", failed_tests)
            col4.metric("Pass Rate", f"{pass_rate:.1f}%")
            
            st.markdown("---")
            
            # Display each test case in a column
            st.subheader("Test Case Results")
            
            for idx, result in enumerate(test_results["results"], 1):
                status_icon = "✅" if result["status"] == "PASSED" else "❌"
                status_color = "green" if result["status"] == "PASSED" else "red"
                
                # Create expander for each test
                with st.expander(f"{status_icon} **{result['test_id']}** - {result['status']}", expanded=(result["status"] == "FAILED")):
                    col_left, col_right = st.columns([2, 1])
                    
                    with col_left:
                        st.markdown(f"**File:** `{result['file']}`")
                        st.markdown(f"**Function:** `{result['test_name']}`")
                        st.markdown(f"**Status:** :{status_color}[**{result['status']}**]")
                        
                        # Show failure details if failed
                        if result["status"] == "FAILED" and result["reason"]:
                            st.markdown("**❗ Failure Reason:**")
                            st.error(result["reason"])
                    
                    with col_right:
                        screenshot_count = result.get("screenshot_count", 0)
                        st.metric("📸 Screenshots", screenshot_count)
                    
                    # Display screenshots if available
                    screenshots = result.get("screenshots", [])
                    if screenshots:
                        st.markdown("---")
                        st.markdown("### 📸 Test Execution Screenshots")
                        st.caption("Screenshots captured during test execution, showing each step:")
                        
                        # Create columns for screenshots (3 per row)
                        for i in range(0, len(screenshots), 3):
                            cols = st.columns(3)
                            for j, col in enumerate(cols):
                                if i + j < len(screenshots):
                                    screenshot_path = Path(screenshots[i + j])
                                    if screenshot_path.exists():
                                        with col:
                                            # Extract step info from filename
                                            step_name = screenshot_path.stem[3:]  # Remove number prefix
                                            st.image(
                                                str(screenshot_path),
                                                caption=f"Step {i + j + 1}: {step_name}",
                                                use_container_width=True
                                            )
                    else:
                        st.info("No screenshots captured for this test.")
            
            # Full output in expander
            with st.expander("📋 View Full Test Output"):
                st.text(test_results["stdout"])
                if test_results["stderr"]:
                    st.markdown("**Standard Error:**")
                    st.text(test_results["stderr"])
        else:
            st.warning("⚠️ No test results were parsed from the output.")
            
            # Show raw output for debugging
            st.markdown("#### Debug Information")
            st.info(f"**Return Code:** {test_results.get('return_code', 'N/A')}")
            
            if test_results["stdout"]:
                with st.expander("📋 View Raw stdout (for debugging)", expanded=True):
                    st.text(test_results["stdout"])
            else:
                st.warning("No stdout captured")
            
            if test_results["stderr"]:
                with st.expander("❌ View stderr", expanded=True):
                    st.error(test_results["stderr"])
            else:
                st.info("No stderr captured")
    
    # Show exploration results only if flag is True
    if graph and plan and show_exploration:
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
