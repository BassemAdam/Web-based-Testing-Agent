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
import os
from datetime import datetime


class PageExplorerState(BaseAgentState):
    """Extended state for page exploration."""
    url: str = ""
    page_structure: PageStructure = None
    exploration_phase: str = "initial"  # initial, dom, visual, interactive, synthesis
    session_id: str = "default"
    raw_data: dict = Field(default_factory=dict)  # Store intermediate exploration data
    scratchpad: str = ""  # Accumulate knowledge here


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

Your goal is to deeply understand a web page by analyzing its DOM structure incrementally.

You will be provided with chunks of the DOM tree. Your task is to:
1. Analyze the current chunk.
2. Identify interactive elements, sections, and potential flows.
3. Update your "scratchpad" with new findings.
4. Maintain a coherent understanding of the page structure across chunks.

The scratchpad is your memory. It should contain:
- List of interactive elements found so far (with locators).
- Page sections identified.
- Any potential interaction flows.
- Notes on page structure.

Be concise but thorough. Focus on actionable information for test automation."""

    def start_point(self, url: str, session_id: str = "default") -> PageExplorerState:
        """Initialize exploration for a given URL."""
        state = PageExplorerState(session_id=session_id, url=url)
        return state

    def run(self, state: PageExplorerState) -> PageExplorerState:
        """Execute one exploration iteration. (Not used in new flow but kept for compatibility)"""
        return state
    
    def explore(self, url: str, session_id: str = "default", output_file: str = None) -> PageStructure:
        """
        Main entry point: Explore a URL and return PageStructure.
        Optimized for weak LLMs using batch processing and scratchpad.
        """
        logger.info(f"🚀 Starting exploration of: {url}")
        
        # 1. Navigate to URL
        logger.info("🌐 Navigating to URL...")
        self.tool_registry.get("goto_url")(url=url, session_id=session_id)
        
        # 2. Extract DOM Tree
        logger.info("📄 Extracting DOM tree...")
        dom_json_str = self.tool_registry.get("extract_dom_tree")(session_id=session_id)
        
        # 3. Save DOM to file
        dom_file = "dom_dump.json"
        with open(dom_file, "w", encoding="utf-8") as f:
            f.write(dom_json_str)
        logger.info(f"💾 Saved DOM dump to: {dom_file}")
        
        # 4. Process DOM in batches
        logger.info("🔄 Processing DOM in batches...")
        scratchpad = "Initial Scratchpad: No knowledge yet."
        
        # Parse JSON to get lines or structure - treating it as text lines for now as requested
        dom_lines = dom_json_str.split('\n')
        total_lines = len(dom_lines)
        batch_size = 50  # Adjustable batch size
        
        for i in range(0, total_lines, batch_size):
            batch_lines = dom_lines[i:i+batch_size]
            batch_content = "\n".join(batch_lines)
            
            logger.info(f"Processing batch {i//batch_size + 1}/{(total_lines//batch_size) + 1} (Lines {i}-{i+len(batch_lines)})")
            
            prompt = f"""
Current Scratchpad:
{scratchpad}

---
New DOM Chunk (Lines {i} to {i+len(batch_lines)}):
{batch_content}
---

Task:
Update the scratchpad with information from the new DOM chunk.
- Identify new interactive elements (buttons, inputs, links).
- Identify page sections.
- Refine existing knowledge.
- Keep the scratchpad organized.

Return ONLY the updated scratchpad content.
"""
            # Create a temporary state for this interaction
            temp_state = PageExplorerState(session_id=session_id, url=url)
            temp_state.add_message(role="system", content=self.system_prompt)
            temp_state.add_message(role="user", content=prompt)
            
            # Pass tools=[] to prevent LLM from trying to use tools
            response = self.llm_generate(temp_state, tools=[])
            new_scratchpad = response.get("content", "")
            if new_scratchpad:
                new_scratchpad = new_scratchpad.strip()
            
            if new_scratchpad:
                scratchpad = new_scratchpad
                logger.debug("Updated scratchpad")
        
        # 5. Final Synthesis
        logger.info("🔧 Synthesizing final page structure...")
        final_structure = self._synthesize_from_scratchpad(url, scratchpad)
        
        # Save to file if requested
        if output_file:
            final_structure.to_json_file(output_file)
            logger.info(f"💾 Saved exploration results to: {output_file}")
            
            # Also save the final scratchpad for debugging
            with open("scratchpad_final.txt", "w", encoding="utf-8") as f:
                f.write(scratchpad)
        
        logger.info("🎉 Exploration complete!")
        return final_structure

    def _synthesize_from_scratchpad(self, url: str, scratchpad: str) -> PageStructure:
        """
        Ask the LLM to convert the final scratchpad into a JSON structure matching PageStructure.
        """
        prompt = f"""
Final Scratchpad:
{scratchpad}

---
Task:
Convert the information in the scratchpad into a structured JSON format.
The JSON should have the following keys:
- elements: List of interactive elements (id, type, locators, description).
- sections: List of page sections.
- flows: List of potential interaction flows.
- technologies: List of detected technologies.

Return ONLY the JSON object.
"""
        state = PageExplorerState(url=url)
        state.add_message(role="system", content="You are a data extraction assistant. Output valid JSON only.")
        state.add_message(role="user", content=prompt)
        
        # Pass tools=[] to prevent LLM from trying to use tools
        response = self.llm_generate(state, tools=[])
        content = response.get("content", "")
        
        # Clean up code blocks if present
        if content and "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif content and "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        try:
            data = json.loads(content)
            
            # Convert to PageStructure objects
            elements = []
            for elem in data.get("elements", []):
                elements.append(ElementCandidate(
                    element_id=elem.get("id", "unknown"),
                    element_type=elem.get("type", "unknown"),
                    locators=elem.get("locators", {}),
                    description=elem.get("description", ""),
                    is_interactive=True
                ))
                
            sections = []
            for sec in data.get("sections", []):
                sections.append(PageSection(
                    section_id=sec.get("id", "unknown"),
                    section_type=sec.get("type", "unknown"),
                    description=sec.get("description", "")
                ))
                
            return PageStructure(
                url=url,
                page_title="Explored Page",
                exploration_timestamp=datetime.now().isoformat(),
                elements=elements,
                sections=sections,
                flows=[], # TODO: Parse flows if needed
                technologies_detected=data.get("technologies", []),
                total_elements_found=len(elements),
                exploration_strategy="scratchpad-batch"
            )
            
        except Exception as e:
            logger.error(f"Failed to parse final JSON: {e}")
            # Return empty structure with error note
            return PageStructure(
                url=url,
                page_title="Error Parsing Results",
                exploration_timestamp=datetime.now().isoformat(),
                elements=[],
                sections=[],
                flows=[],
                technologies_detected=[],
                total_elements_found=0,
                exploration_strategy="scratchpad-batch-failed"
            )
