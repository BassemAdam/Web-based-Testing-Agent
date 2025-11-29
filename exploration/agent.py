"""
Phase 1 Exploration Agent

This agent explores a web page to build deep understanding of:
- Structure (DOM hierarchy)
- Interactive elements (buttons, forms, links)
- Visual layout (screenshots, positioning)
- Behavior (dynamic content, flows)

The agent produces a PageStructure object as "ground truth" for test generation.
"""

from agent.base import Agent, BaseAgentState
from llm.base import LLMClient
from tools.registry import ToolRegistry
from exploration.models import (
    PageStructure, ElementCandidate, PageSection, 
    InteractionFlow, VisualSignature
)
from pydantic import Field
from loguru import logger
import json
from datetime import datetime


class PageExplorerState(BaseAgentState):
    """Extended state for page exploration."""
    url: str = ""
    page_structure: PageStructure = None
    exploration_phase: str = "initial"  # initial, dom, visual, interactive, synthesis
    session_id: str = "default"
    raw_data: dict = Field(default_factory=dict)  # Store intermediate exploration data


class PageExplorerAgent(Agent):
    """
    Agent that explores a web page and produces structured knowledge.
    
    Exploration Strategy:
    1. Initial navigation & screenshot
    2. DOM analysis (structure, elements, sections)
    3. Visual analysis (layout, groupings)
    4. Interactive exploration (flows, dynamic content)
    5. Synthesis into PageStructure
    """
    
    def __init__(self, llm: LLMClient, tool_registry: ToolRegistry, max_iterations: int = 20):
        super().__init__(llm, tool_registry, max_iterations)
        self.system_prompt = """You are an expert web page exploration agent for test automation.

Your goal is to deeply understand a web page by:
1. Analyzing its DOM structure
2. Identifying all interactive elements with multiple locator strategies
3. Understanding visual layout and groupings
4. Detecting interaction flows (login, search, navigation, etc.)
5. Finding dynamic content areas

You have access to tools for:
- Navigation: goto_url
- DOM Analysis: extract_dom_tree, extract_interactive_elements, extract_accessibility_tree, detect_page_sections, detect_technologies
- Visual Analysis: take_full_page_screenshot, take_element_screenshot, extract_visual_layout, detect_visual_groups
- Interactive Exploration: explore_clickable_elements, detect_dynamic_content, detect_interaction_flows, explore_hover_effects

CRITICAL INSTRUCTIONS:
1. Use tools systematically - don't skip steps
2. For each interactive element, capture multiple locator strategies (id, css, text, role, xpath)
3. Take screenshots for visual signatures (self-healing capability)
4. Look for both obvious and hidden interactive elements
5. Detect multi-step flows (login, checkout, etc.)
6. When you have thoroughly explored the page, respond with a final summary

Process:
- Start by navigating to the URL
- Extract DOM tree and interactive elements
- Take full page screenshot
- Detect page sections and flows
- Identify technologies in use
- Summarize findings when complete

When ready to finish, say "EXPLORATION_COMPLETE" and provide a comprehensive summary."""

    def start_point(self, url: str, session_id: str = "default") -> PageExplorerState:
        """Initialize exploration for a given URL."""
        state = PageExplorerState(session_id=session_id, url=url)
        
        # Add system message
        state.add_message(
            role="system",
            content=self.system_prompt
        )
        
        # Add user request
        state.add_message(
            role="user",
            content=f"""Explore this web page thoroughly: {url}

Your task is to build a complete understanding of this page for test automation purposes.

Start by navigating to the URL, then systematically explore using all available tools.
Document all interactive elements, page sections, visual layout, and interaction flows.

Take your time and be thorough - this exploration will be the foundation for generating automated tests."""
        )
        
        return state

    def run(self, state: PageExplorerState) -> PageExplorerState:
        """Execute one exploration iteration."""
        logger.info(f"🔍 Iteration {state.iteration + 1} - Phase: {state.exploration_phase}")
        
        # Get LLM response
        response = self.llm_generate(state)
        
        # Add assistant message
        assistant_content = response.get("content", "") or ""
        state.add_message(
            role="assistant",
            content=assistant_content,
            tool_calls=response.get("tool_calls")
        )
        
        # Check if exploration is complete
        if assistant_content and "EXPLORATION_COMPLETE" in assistant_content.upper():
            logger.info("✅ Exploration marked as complete by agent")
            state.is_finished = True
            return state
        
        # Handle tool calls
        tool_calls = response.get("tool_calls", [])
        if tool_calls:
            for tool_call in tool_calls:
                # Execute tool
                tool_result = self.call_tool(tool_call)
                
                # Store raw data for synthesis
                func_name = tool_call["function"]["name"]
                try:
                    result_content = json.loads(tool_result["content"])
                    if func_name not in state.raw_data:
                        state.raw_data[func_name] = []
                    state.raw_data[func_name].append(result_content)
                except:
                    pass  # Not all results are JSON
                
                # Add tool result to messages
                state.add_message(**tool_result)
            
            logger.info(f"✅ Executed {len(tool_calls)} tool(s)")
        
        # No tool calls and not finished - might be stuck
        elif not state.is_finished:
            logger.warning("⚠️  No tool calls and not finished - prompting agent to continue")
            state.add_message(
                role="user",
                content="Continue exploring. Use your tools to gather more information about the page, or say EXPLORATION_COMPLETE if you have gathered enough data."
            )
        
        return state
    
    def synthesize_page_structure(self, state: PageExplorerState) -> PageStructure:
        """
        Synthesize all exploration data into a structured PageStructure object.
        This happens after the agent completes exploration.
        """
        logger.info("🔧 Synthesizing page structure from exploration data...")
        
        # Extract elements from interactive_elements data
        elements = []
        if "extract_interactive_elements" in state.raw_data:
            for data in state.raw_data["extract_interactive_elements"]:
                if isinstance(data, list):
                    for idx, elem in enumerate(data):
                        element = ElementCandidate(
                            element_id=f"elem_{idx}",
                            element_type=elem.get("type", "unknown"),
                            locators=elem.get("locators", {}),
                            description=elem.get("visible_text", "")[:100] or f"{elem.get('type')} element",
                            is_interactive=True,
                            expected_actions=self._infer_actions(elem),
                            initial_state=elem.get("attributes", {})
                        )
                        
                        # Add visual signature if we have position data
                        if "position" in elem:
                            element.visual_signature = VisualSignature(
                                bounding_box=elem["position"],
                                visible_text=elem.get("visible_text")
                            )
                        
                        elements.append(element)
        
        # Extract sections
        sections = []
        if "detect_page_sections" in state.raw_data:
            for data in state.raw_data["detect_page_sections"]:
                if isinstance(data, list):
                    for sec in data:
                        section = PageSection(
                            section_id=sec.get("id", "unknown"),
                            section_type=sec.get("type", "unknown"),
                            description=f"{sec.get('type')} section with {sec.get('interactive_count', 0)} interactive elements"
                        )
                        sections.append(section)
        
        # Extract flows
        flows = []
        if "detect_interaction_flows" in state.raw_data:
            for data in state.raw_data["detect_interaction_flows"]:
                if isinstance(data, list):
                    for flow_data in data:
                        flow = InteractionFlow(
                            flow_id=flow_data.get("form_id", f"flow_{len(flows)}"),
                            flow_name=flow_data.get("flow_type", "unknown"),
                            steps=flow_data.get("steps", []),
                            entry_point=flow_data.get("steps", [{}])[0].get("element", "unknown") if flow_data.get("steps") else "unknown"
                        )
                        flows.append(flow)
        
        # Extract technologies
        technologies = []
        if "detect_technologies" in state.raw_data:
            for data in state.raw_data["detect_technologies"]:
                if isinstance(data, list):
                    technologies.extend(data)
        
        # Get full page screenshot
        full_page_screenshot = None
        if "take_full_page_screenshot" in state.raw_data:
            screenshots = state.raw_data["take_full_page_screenshot"]
            if screenshots and isinstance(screenshots[-1], str):
                full_page_screenshot = screenshots[-1]
        
        # Create PageStructure
        page_structure = PageStructure(
            url=state.url,
            page_title="Explored Page",  # Could extract from goto_url result
            exploration_timestamp=datetime.now().isoformat(),
            elements=elements,
            sections=sections,
            flows=flows,
            technologies_detected=list(set(technologies)),
            full_page_screenshot=full_page_screenshot,
            total_elements_found=len(elements),
            exploration_depth=state.iteration,
            exploration_strategy="hybrid"
        )
        
        logger.info(f"✅ Synthesized structure: {len(elements)} elements, {len(sections)} sections, {len(flows)} flows")
        return page_structure
    
    def _infer_actions(self, elem: dict) -> list:
        """Infer possible actions based on element type and attributes."""
        actions = []
        elem_type = elem.get("type", "")
        attributes = elem.get("attributes", {})
        
        if elem_type in ["button", "a"]:
            actions.append("click")
        elif elem_type == "input":
            input_type = attributes.get("type", "text")
            if input_type in ["text", "email", "password", "search", "tel", "url"]:
                actions.extend(["fill", "clear"])
            elif input_type in ["checkbox", "radio"]:
                actions.append("check")
            elif input_type == "submit":
                actions.append("click")
        elif elem_type == "select":
            actions.append("select_option")
        elif elem_type == "textarea":
            actions.extend(["fill", "clear"])
        
        return actions or ["interact"]
    
    def explore(self, url: str, session_id: str = "default", output_file: str = None) -> PageStructure:
        """
        Main entry point: Explore a URL and return PageStructure.
        
        Args:
            url: The URL to explore
            session_id: Browser session ID
            output_file: Optional path to save JSON output
        
        Returns:
            PageStructure object with complete exploration results
        """
        logger.info(f"🚀 Starting exploration of: {url}")
        
        # Run exploration
        final_state = self.iterate(url=url, session_id=session_id)
        
        # Synthesize results
        page_structure = self.synthesize_page_structure(final_state)
        
        # Save to file if requested
        if output_file:
            page_structure.to_json_file(output_file)
            logger.info(f"💾 Saved exploration results to: {output_file}")
        
        logger.info("🎉 Exploration complete!")
        return page_structure
