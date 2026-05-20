#!/usr/bin/env python
import sys
from pathlib import Path
import json

import streamlit as st
import asyncio
import pandas as pd

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
from agent.pipelines.agent_explorer import AgentSiteExplorer
from agent.pipelines.multi_page_test_design_pipeline import MultiPageTestDesignPipeline
from agent.visualization.coverage_overlay import create_page_coverage_overlay
from agent.models.site_graph import SiteGraph, PageNode, NavEdge
from agent.models.page_snapshot import PageSnapshot
from agent.models.element_descriptor import ElementDescriptor
from agent.metrics.metrics_recorder import get_metrics_tracker, get_global_metrics, clear_global_metrics
from test_runner import TestRunner
from dataclasses import asdict


# ---------------------------------------------------------------------
# JSON File Paths
# ---------------------------------------------------------------------
SNAPSHOT_PATH = ROOT / "src" / "artifacts" / "snapshots" / "site_snapshot.json"
TEST_PLAN_PATH = ROOT / "src" / "artifacts" / "test_plans" / "test_plan.json"
GENERATED_TESTS_DIR = ROOT / "artifacts" / "generated_tests" / "tests"

# Available models
AVAILABLE_MODELS = [
    "gpt-5-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "deepseek-coder-v2:16b",
    "llama3.1:8b",
    "codellama:13b",
]


# ---------------------------------------------------------------------
# Helpers to load/save from JSON files
# ---------------------------------------------------------------------
def load_snapshot_from_file() -> tuple[SiteGraph | None, dict | None]:
    """Load site graph from snapshot JSON file."""
    if not SNAPSHOT_PATH.exists():
        return None, None
    
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        graph = SiteGraph()
        
        for page_id, page_data in data.get("pages", {}).items():
            snapshot_data = page_data.get("snapshot", {})
            
            # Rebuild elements
            elements = []
            for elem_data in snapshot_data.get("elements", []):
                elem = ElementDescriptor(
                    id=elem_data.get("id", ""),
                    tag=elem_data.get("tag", ""),
                    text=elem_data.get("text", ""),
                    role=elem_data.get("role"),
                    aria_label=elem_data.get("aria_label"),
                    name=elem_data.get("name"),
                    type=elem_data.get("type"),
                    css_selector=elem_data.get("css_selector", ""),
                    xpath=elem_data.get("xpath", ""),
                    attributes=elem_data.get("attributes", {}),
                    classes=elem_data.get("classes", []),
                    bounding_box=elem_data.get("bounding_box"),
                )
                elements.append(elem)
            
            snapshot = PageSnapshot(
                url=snapshot_data.get("url", ""),
                title=snapshot_data.get("title", ""),
                raw_html=snapshot_data.get("raw_html", ""),
                elements=elements,
                screenshot_path=snapshot_data.get("screenshot_path"),
                summary=snapshot_data.get("summary"),
                meta=snapshot_data.get("meta"),
            )
            
            node = PageNode(id=page_id, snapshot=snapshot)
            graph.pages[page_id] = node
        
        # Rebuild edges
        for edge_data in data.get("edges", []):
            edge = NavEdge(
                from_page_id=edge_data.get("from_page_id", ""),
                to_page_id=edge_data.get("to_page_id", ""),
                element_key=edge_data.get("element_key", ""),
                description=edge_data.get("description", ""),
            )
            graph.edges.append(edge)
            # Set incoming edge on target node
            if edge.to_page_id in graph.pages:
                graph.pages[edge.to_page_id].incoming_edge = edge
        
        return graph, data
    except Exception as e:
        st.error(f"Failed to load snapshot: {e}")
        return None, None


def load_plan_from_file() -> dict | None:
    """Load test plan from JSON file."""
    if not TEST_PLAN_PATH.exists():
        return None
    
    try:
        with open(TEST_PLAN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load test plan: {e}")
        return None


def get_generated_test_files() -> list[Path]:
    """Get list of generated test files."""
    if not GENERATED_TESTS_DIR.exists():
        return []
    return sorted(GENERATED_TESTS_DIR.glob("test_*.py"))


def save_snapshot_to_file(graph: SiteGraph, start_url: str, meta: dict = None):
    """Save site graph to snapshot JSON file."""
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    pages_data = {}
    for pid, node in graph.pages.items():
        pages_data[pid] = {
            "snapshot": {
                "url": node.snapshot.url,
                "title": node.snapshot.title,
                "raw_html": node.snapshot.raw_html,
                "elements": [asdict(e) for e in node.snapshot.elements],
                "screenshot_path": node.snapshot.screenshot_path,
                "summary": node.snapshot.summary,
                "meta": node.snapshot.meta or {},
            },
        }
    
    data = {
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
        "meta": meta or {},
    }
    
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def save_plan_to_file(plan: dict):
    """Save test plan to JSON file."""
    TEST_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert TestCase objects to dicts if needed
    test_cases = plan.get("test_cases", [])
    serializable_tcs = []
    for tc in test_cases:
        if hasattr(tc, "id"):  # It's a TestCase object
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
        else:
            serializable_tcs.append(tc)
    
    plan_data = {
        "start_url": plan.get("start_url", ""),
        "snapshot_file": str(SNAPSHOT_PATH),
        "test_cases": serializable_tcs,
        "element_coverage": plan.get("coverage", {}),
        "coverage_summary": plan.get("coverage_summary", ""),
    }
    
    with open(TEST_PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)


# ---------------------------------------------------------------------
# Helpers to cache / store state
# ---------------------------------------------------------------------
def get_designer(model_name: str | None):
    return MultiPageTestDesignPipeline(model_name=model_name)


def run_exploration(start_url: str, max_depth: int, max_pages: int, max_links: int, use_agent: bool = False):
    if use_agent:
        explorer = AgentSiteExplorer(
            max_depth=max_depth,
            max_pages=max_pages,
            max_actions_per_page=max_links,
        )
    else:
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
        use_agent = st.checkbox(
            "🤖 Use AI Agent Explorer",
            value=False,
            help="Use AI agent for intelligent exploration instead of rule-based",
        )
        
        st.markdown("---")
        st.subheader("🤖 Model Selection")
        
        # Model provider selection
        model_provider = st.selectbox(
            "LLM Provider",
            options=["Copilot (GitHub)", "Ollama (Local)", "Custom"],
            index=0,
            help="Choose your LLM provider",
        )
        
        if model_provider == "Copilot (GitHub)":
            model_name = st.selectbox(
                "Model",
                options=AVAILABLE_MODELS,
                index=0,
                help="Select Copilot model",
            )
        elif model_provider == "Ollama (Local)":
            model_name = st.selectbox(
                "Model",
                options=["deepseek-coder-v2:16b", "llama3.1:8b", "codellama:13b", "mistral:7b"],
                index=0,
                help="Select Ollama model",
            )
        else:
            model_name = st.text_input(
                "Custom Model Name",
                value="gpt-5-mini",
                help="Enter custom model name",
            )

        st.markdown("---")
        st.subheader("💬 Feedback & Refinement")
        
        # Main feedback type selection
        feedback_type = st.radio(
            "Feedback Target",
            options=["Test Plan", "Code Generation"],
            index=0,
            help="Choose what to provide feedback on",
        )
        
        # Initialize variables
        target_test_case = None
        code_feedback_scope = None
        target_test_file = None
        
        if feedback_type == "Test Plan":
            st.info("📋 Feedback will be applied to the test plan (test_plan.json)")
            
            # Load existing test cases for reference
            existing_plan = load_plan_from_file()
            if existing_plan and existing_plan.get("test_cases"):
                tc_options = ["All Test Cases"] + [tc.get("id", "Unknown") for tc in existing_plan["test_cases"]]
                target_test_case = st.selectbox(
                    "Target Test Case",
                    options=tc_options,
                    index=0,
                    help="Choose which test case to focus feedback on (or all)",
                )
                if target_test_case == "All Test Cases":
                    target_test_case = None
            
            feedback_placeholder = "e.g., Add more edge cases for login, include negative tests for form validation..."
            
        else:  # Code Generation
            st.info("🔧 Feedback will be applied to generated test files")
            
            code_feedback_scope = st.radio(
                "Scope",
                options=["All Test Files", "Specific File"],
                index=0,
                help="Apply feedback to all test files or a specific one",
            )
            
            if code_feedback_scope == "Specific File":
                test_files = get_generated_test_files()
                if test_files:
                    file_options = [f.name for f in test_files]
                    target_test_file = st.selectbox(
                        "Select Test File",
                        options=file_options,
                        help="Choose which test file to modify",
                    )
                    
                    # Show file preview
                    if target_test_file:
                        selected_file = GENERATED_TESTS_DIR / target_test_file
                        if selected_file.exists():
                            with st.expander(f"📄 Preview: {target_test_file}", expanded=False):
                                st.code(selected_file.read_text(encoding="utf-8"), language="python")
                else:
                    st.warning("No test files found. Generate tests first.")
            
            feedback_placeholder = "e.g., Add explicit waits before assertions, use page.wait_for_selector()..."
        
        feedback = st.text_area(
            "Your Feedback",
            value="",
            placeholder=feedback_placeholder,
            height=120,
            help="Describe the changes or improvements you want",
        )
        
        # Refine button in feedback section
        refine_btn = st.button(
            "🔁 Apply Feedback",
            use_container_width=True,
            type="primary",
            help=f"Apply feedback to {'test plan' if feedback_type == 'Test Plan' else 'code generation'}",
        )

        st.markdown("---")
        st.subheader("🔄 Actions")
        
        col_load, col_run = st.columns(2)
        load_btn = col_load.button("📂 Load from Files", use_container_width=True)
        run_btn = col_run.button("🚀 Explore + Generate", use_container_width=True)
        
        save_btn = st.button("💾 Save to Files", use_container_width=True)
        
        st.markdown("---")
        st.subheader("🧪 Test Execution")
        
        selfheal_enabled = st.checkbox(
            "🔄 Enable Self-Healing",
            value=True,
            help="Automatically regenerate failed tests with error feedback"
        )
        
        col_gen, col_run_tests = st.columns(2)
        generate_tests_btn = col_gen.button("🔧 Generate Tests", use_container_width=True)
        run_tests_btn = col_run_tests.button("▶️ Run Tests", use_container_width=True, type="primary")
        
        # Show file status
        st.markdown("---")
        st.subheader("📁 File Status")
        snapshot_exists = SNAPSHOT_PATH.exists()
        plan_exists = TEST_PLAN_PATH.exists()
        test_files = get_generated_test_files()
        st.markdown(f"- Snapshot: {'✅' if snapshot_exists else '❌'} `{SNAPSHOT_PATH.name}`")
        st.markdown(f"- Test Plan: {'✅' if plan_exists else '❌'} `{TEST_PLAN_PATH.name}`")
        st.markdown(f"- Test Files: {'✅' if test_files else '❌'} `{len(test_files)} files`")

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
    if "metrics" not in st.session_state:
        st.session_state.metrics = None

    # --- Load from files --------------------------------------------------
    if load_btn:
        with st.spinner("Loading from JSON files..."):
            graph, snapshot_data = load_snapshot_from_file()
            plan = load_plan_from_file()
            
            # Clear metrics for fresh session
            clear_global_metrics()
            
            if graph:
                st.session_state.graph = graph
                st.session_state.start_url = snapshot_data.get("start_url", "") if snapshot_data else ""
                st.success(f"✅ Loaded snapshot with {len(graph.pages)} pages")
            else:
                st.warning("No snapshot file found. Run exploration first.")
            
            if plan:
                # Convert plan to expected format
                st.session_state.plan = {
                    "test_cases": plan.get("test_cases", []),
                    "coverage": plan.get("element_coverage", {}),
                    "coverage_summary": plan.get("coverage_summary", ""),
                    "start_url": plan.get("start_url", ""),
                }
                st.success(f"✅ Loaded test plan with {len(plan.get('test_cases', []))} test cases")
            else:
                st.warning("No test plan file found.")
            
            st.session_state.show_exploration = True

    # --- Save to files ----------------------------------------------------
    if save_btn:
        with st.spinner("Saving to JSON files..."):
            if st.session_state.graph and st.session_state.start_url:
                save_snapshot_to_file(st.session_state.graph, st.session_state.start_url)
                st.success(f"✅ Saved snapshot to {SNAPSHOT_PATH}")
            else:
                st.warning("No graph in memory to save.")
            
            if st.session_state.plan:
                plan_to_save = st.session_state.plan.copy()
                plan_to_save["start_url"] = st.session_state.start_url
                save_plan_to_file(plan_to_save)
                st.success(f"✅ Saved test plan to {TEST_PLAN_PATH}")
            else:
                st.warning("No plan in memory to save.")

    # --- Run full pipeline ------------------------------------------------
    if run_btn:
        # Clear metrics for new exploration
        metrics_tracker = get_metrics_tracker()
        metrics_tracker.reset()
        
        with st.spinner("Exploring site and generating initial test plan..."):
            graph = run_exploration(start_url, max_depth, max_pages, max_links, use_agent)
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
            
            # Auto-save snapshot and plan to files
            save_snapshot_to_file(graph, start_url, meta={
                "max_depth": max_depth,
                "max_pages": max_pages,
                "max_links_per_page": max_links,
                "use_agent": use_agent,
            })
            save_plan_to_file(plan_dict)

        st.success(f"✅ Exploration complete! Saved snapshot ({len(graph.pages)} pages) and test plan to files.")

    # --- Refinement with feedback ----------------------------------------
    if refine_btn:
        fb = feedback.strip()
        if not fb:
            st.warning("Please type some feedback before applying.")
        elif feedback_type == "Test Plan":
            # Test Plan Feedback
            if not st.session_state.graph:
                st.warning("Load or run exploration first to refine the test plan.")
            else:
                with st.spinner("Refining test plan with your feedback..."):
                    graph = st.session_state.graph
                    designer = get_designer(model_name or None)
                    
                    # Build structured feedback
                    if target_test_case:
                        structured_feedback = f"[FOCUS ON TEST CASE: {target_test_case}] {fb}"
                    else:
                        structured_feedback = f"[TEST PLAN FEEDBACK] {fb}"
                    
                    # Rebuild plan with feedback
                    plan_dict = designer.build_plan(graph, human_feedback=structured_feedback)
                    plan_dict["start_url"] = st.session_state.start_url
                    st.session_state.plan = plan_dict

                    # Regenerate overlays based on new coverage
                    overlays = generate_overlays(graph, plan_dict["coverage"])
                    st.session_state.overlays = overlays
                    
                    # Auto-save to file
                    save_plan_to_file(plan_dict)

                st.success("✅ Test plan refined and saved!")
                
        else:  # Code Generation Feedback
            test_files = get_generated_test_files()
            if not test_files:
                st.warning("No test files found. Generate tests first.")
            else:
                with st.spinner("Applying feedback to test code..."):
                    plan_path = str(TEST_PLAN_PATH)
                    
                    if code_feedback_scope == "Specific File" and target_test_file:
                        # Regenerate specific test file
                        success = test_runner.generate_tests(
                            plan_path=plan_path,
                            feedback=fb,
                            test_filename=target_test_file
                        )
                        
                        # Update metrics after code generation with feedback
                        metrics_tracker = get_metrics_tracker()
                        st.session_state.metrics = metrics_tracker.get_session_metrics().to_dict()
                        
                        if success:
                            st.success(f"✅ Regenerated {target_test_file} with feedback!")
                        else:
                            st.error(f"❌ Failed to regenerate {target_test_file}")
                    else:
                        # Regenerate all test files
                        success = test_runner.generate_tests(
                            plan_path=plan_path,
                            feedback=fb,
                            test_filename=None
                        )
                        
                        # Update metrics after code generation with feedback
                        metrics_tracker = get_metrics_tracker()
                        st.session_state.metrics = metrics_tracker.get_session_metrics().to_dict()
                        
                        if success:
                            st.success("✅ Regenerated all test files with feedback!")
                        else:
                            st.error("❌ Failed to regenerate test files")
                
                # Force rerun to update metrics display
                st.rerun()

    # --- Generate Tests ---------------------------------------------------
    if generate_tests_btn:
        plan_path = None
        
        # Priority: Check session first, then disk
        if st.session_state.plan:
            # Save current plan to file first
            plan_to_save = st.session_state.plan.copy()
            plan_to_save["start_url"] = st.session_state.start_url
            save_plan_to_file(plan_to_save)
            plan_path = str(TEST_PLAN_PATH)
        elif TEST_PLAN_PATH.exists():
            plan_path = str(TEST_PLAN_PATH)
            st.info("Using existing test plan from disk.")
        else:
            st.warning("Please generate a test plan first.")
        
        if plan_path:
            with st.spinner("Generating test code..."):
                success = test_runner.generate_tests(plan_path)
                
                if success:
                    st.session_state.tests_generated = True
                    st.success("✅ Test code generated successfully!")
                else:
                    st.error("❌ Failed to generate test code.")
        
        # Force UI refresh to show updated metrics
        st.rerun()
    
    # --- Run Tests --------------------------------------------------------
    if run_tests_btn:
        tests_dir = ROOT / "artifacts" / "generated_tests" / "tests"
        if not tests_dir.exists() or not list(tests_dir.glob("test_*.py")):
            st.warning("Please generate tests first using the '🔧 Generate Tests' button.")
        else:
            with st.spinner("Running tests..."):
                test_execution_result = test_runner.run_tests(selfheal=selfheal_enabled)
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
    
    # Always get metrics from global storage
    metrics = get_global_metrics()

    # Display Performance Metrics Section
    if metrics and metrics.get("phases"):
        st.markdown("---")
        st.header("📊 Performance Metrics")
        
        # Display totals in a nice format
        totals = metrics.get("totals", {})
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "⏱️ Total Time",
                f"{totals.get('total_response_time_seconds', 0):.2f}s"
            )
        with col2:
            st.metric(
                "🔤 Total Tokens",
                f"{totals.get('total_tokens', 0):,}"
            )
        with col3:
            st.metric(
                "🔄 LLM Calls",
                totals.get('total_llm_calls', 0)
            )
        with col4:
            st.metric(
                "⚡ Avg Time/Call",
                f"{totals.get('avg_response_time_per_call', 0):.2f}s"
            )
        
        # Display per-phase breakdown
        st.subheader("Phase Breakdown")
        
        phases = metrics.get("phases", {})
        if phases:
            # Create a DataFrame for the table
            phase_rows = []
            for phase_name, phase_metrics in phases.items():
                phase_rows.append({
                    "Phase": phase_name,
                    "Response Time (s)": round(phase_metrics.get('response_time_seconds', 0), 3),
                    "Prompt Tokens": phase_metrics.get('prompt_tokens', 0),
                    "Completion Tokens": phase_metrics.get('completion_tokens', 0),
                    "Total Tokens": phase_metrics.get('total_tokens', 0),
                    "LLM Calls": phase_metrics.get('llm_calls', 0),
                    "Avg Time/Call (s)": round(phase_metrics.get('avg_response_time_per_call', 0), 3),
                })
            
            # Add totals row if more than one phase
            if len(phase_rows) > 1:
                phase_rows.append({
                    "Phase": "📊 TOTAL",
                    "Response Time (s)": round(totals.get('total_response_time_seconds', 0), 3),
                    "Prompt Tokens": totals.get('total_prompt_tokens', 0),
                    "Completion Tokens": totals.get('total_completion_tokens', 0),
                    "Total Tokens": totals.get('total_tokens', 0),
                    "LLM Calls": totals.get('total_llm_calls', 0),
                    "Avg Time/Call (s)": round(totals.get('avg_response_time_per_call', 0), 3),
                })
            
            df = pd.DataFrame(phase_rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Add bar charts for visual comparison (only if multiple phases)
            if len(phases) > 1:
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    st.markdown("**⏱️ Response Time by Phase**")
                    time_df = pd.DataFrame({
                        "Phase": [p["Phase"] for p in phase_rows if p["Phase"] != "📊 TOTAL"],
                        "Seconds": [p["Response Time (s)"] for p in phase_rows if p["Phase"] != "📊 TOTAL"]
                    })
                    st.bar_chart(time_df.set_index("Phase"))
                
                with col_chart2:
                    st.markdown("**🔤 Tokens Used by Phase**")
                    token_df = pd.DataFrame({
                        "Phase": [p["Phase"] for p in phase_rows if p["Phase"] != "📊 TOTAL"],
                        "Tokens": [p["Total Tokens"] for p in phase_rows if p["Phase"] != "📊 TOTAL"]
                    })
                    st.bar_chart(token_df.set_index("Phase"))

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
                                                use_column_width=True
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
            # Handle both dict and object formats
            tc_id = tc.get("id", "") if isinstance(tc, dict) else tc.id
            tc_name = tc.get("name", "") if isinstance(tc, dict) else tc.name
            tc_desc = tc.get("description", "") if isinstance(tc, dict) else tc.description
            tc_tags = tc.get("tags", []) if isinstance(tc, dict) else tc.tags
            tc_steps = tc.get("steps", []) if isinstance(tc, dict) else tc.steps
            tc_covered = tc.get("covered_element_keys", []) if isinstance(tc, dict) else tc.covered_element_keys
            
            with st.expander(f"{tc_id} – {tc_name}"):
                st.write(tc_desc)
                if tc_tags:
                    st.write("**Tags:**", ", ".join(tc_tags))

                st.markdown("**Steps:**")
                for s in tc_steps:
                    if isinstance(s, dict):
                        st.write(
                            f"- `[ {s.get('page_id', '')} ]` **{s.get('action', '')}** "
                            f"target=`{s.get('target', '')}` – {s.get('details', '')}"
                        )
                    else:
                        st.write(
                            f"- `[ {s.page_id} ]` **{s.action}** "
                            f"target=`{s.target}` – {s.details}"
                        )

                if tc_covered:
                    st.markdown("**Covered element keys:**")
                    for k in tc_covered:
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