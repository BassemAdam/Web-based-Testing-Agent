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
        Optimized for weak LLMs using batch processing and accumulation.
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
        if output_file:
            output_dir = os.path.dirname(output_file)
            if output_dir:
                dom_file = os.path.join(output_dir, "dom_dump.json")

        with open(dom_file, "w", encoding="utf-8") as f:
            f.write(dom_json_str)
        logger.info(f"💾 Saved DOM dump to: {dom_file}")
        
        # 4. Process DOM in batches and accumulate findings
        logger.info("🔄 Processing DOM in batches...")
        
        # Accumulators for findings
        all_elements = []
        all_sections = []
        all_flows = []
        all_technologies = set()
        
        # Parse JSON to get lines or structure
        dom_lines = dom_json_str.split('\n')
        total_lines = len(dom_lines)
        batch_size = 50  # Adjustable batch size
        
        for i in range(0, total_lines, batch_size):
            batch_lines = dom_lines[i:i+batch_size]
            batch_content = "\n".join(batch_lines)
            
            logger.info(f"Processing batch {i//batch_size + 1}/{(total_lines//batch_size) + 1} (Lines {i}-{i+len(batch_lines)})")
            
            prompt = f"""
DOM Chunk (Lines {i} to {i+len(batch_lines)}):
{batch_content}

---
Task:
Analyze this DOM chunk and extract:
1. Interactive elements (buttons, inputs, links, forms).
2. Page sections (header, footer, main, etc.).
3. Detected technologies (libraries, frameworks).

Return a JSON object with the following structure:
{{
  "elements": [
    {{
      "id": "unique_id_or_selector",
      "type": "button/input/link/etc",
      "locators": {{ "css": "...", "xpath": "...", "text": "..." }},
      "description": "What this element does"
    }}
  ],
  "sections": [
    {{
      "id": "section_id",
      "type": "header/footer/etc",
      "description": "Section description"
    }}
  ],
  "technologies": ["React", "Bootstrap", etc]
}}

If no items are found in this chunk, return empty lists.
Output valid JSON only.
"""
            # Create a temporary state for this interaction
            temp_state = PageExplorerState(session_id=session_id, url=url)
            temp_state.add_message(role="system", content="You are a data extraction assistant. Output valid JSON only.")
            temp_state.add_message(role="user", content=prompt)
            
            # Pass tools=[] to prevent LLM from trying to use tools
            response = self.llm_generate(temp_state, tools=[])
            content = response.get("content", "")
            
            # Clean up code blocks if present
            if content and "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif content and "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            try:
                if content.strip():
                    data = json.loads(content)
                    
                    # Accumulate findings
                    if "elements" in data and isinstance(data["elements"], list):
                        all_elements.extend(data["elements"])
                        logger.debug(f"Found {len(data['elements'])} elements in batch")
                        
                    if "sections" in data and isinstance(data["sections"], list):
                        all_sections.extend(data["sections"])
                        
                    if "technologies" in data and isinstance(data["technologies"], list):
                        all_technologies.update(data["technologies"])
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from batch response")
            except Exception as e:
                logger.error(f"Error processing batch: {e}")
        
        # 5. Final Synthesis
        logger.info("🔧 Synthesizing final page structure...")
        
        # Convert accumulated data to PageStructure objects
        final_elements = []
        for idx, elem in enumerate(all_elements):
            # Ensure locators is a dict
            locators = elem.get("locators", {})
            if not isinstance(locators, dict):
                locators = {"raw": str(locators)}
            
            # Handle missing or None ID
            elem_id = elem.get("id")
            if not elem_id:
                elem_id = f"elem_{idx}"

            final_elements.append(ElementCandidate(
                element_id=elem_id,
                element_type=elem.get("type", "unknown"),
                locators=locators,
                description=elem.get("description", "No description"),
                is_interactive=True
            ))
            
        final_sections = []
        for idx, sec in enumerate(all_sections):
            # Handle missing or None ID
            sec_id = sec.get("id")
            if not sec_id:
                sec_id = f"sec_{idx}"

            final_sections.append(PageSection(
                section_id=sec_id,
                section_type=sec.get("type", "unknown"),
                description=sec.get("description", "No description")
            ))
            
        final_structure = PageStructure(
            url=url,
            page_title="Explored Page",
            exploration_timestamp=datetime.now().isoformat(),
            elements=final_elements,
            sections=final_sections,
            flows=[], # Flows are harder to detect in chunks
            technologies_detected=list(all_technologies),
            total_elements_found=len(final_elements),
            exploration_strategy="batch-accumulation"
        )
        
        # Save to file if requested
        if output_file:
            final_structure.to_json_file(output_file)
            logger.info(f"💾 Saved exploration results to: {output_file}")
        
        logger.info("🎉 Exploration complete!")
        return final_structure

    def _synthesize_from_scratchpad(self, url: str, scratchpad: str) -> PageStructure:
        """
        Deprecated: Use batch accumulation instead.
        """
        pass
