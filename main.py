from exploration.agent import PageExplorerAgent
from llm.groq_client import GroqClient
from llm.config import LLMConfig
from tools.registry import ToolRegistry
from loguru import logger
import sys

# Import all exploration tools
from exploration import dom_tools, visual_tools, interactive_tools
from tools.toolkit import web_explorer


def setup_exploration_tools(session_id: str = "default") -> ToolRegistry:
    """Register all tools needed for page exploration."""
    registry = ToolRegistry(session_id=session_id)
    
    # Navigation tools
    registry.register(web_explorer.goto_url)
    registry.register(web_explorer.get_page_content)
    
    # DOM extraction tools
    registry.register(dom_tools.extract_dom_tree)
    registry.register(dom_tools.extract_interactive_elements)
    registry.register(dom_tools.extract_accessibility_tree)
    registry.register(dom_tools.detect_page_sections)
    registry.register(dom_tools.detect_technologies)
    
    # Visual analysis tools
    registry.register(visual_tools.take_full_page_screenshot)
    registry.register(visual_tools.take_element_screenshot)
    registry.register(visual_tools.extract_visual_layout)
    registry.register(visual_tools.detect_visual_groups)
    registry.register(visual_tools.analyze_element_visibility)
    
    # Interactive exploration tools
    registry.register(interactive_tools.explore_clickable_elements)
    registry.register(interactive_tools.detect_dynamic_content)
    registry.register(interactive_tools.detect_interaction_flows)
    registry.register(interactive_tools.explore_hover_effects)
    registry.register(interactive_tools.test_interactive_element)
    
    logger.info(f"✅ Registered {len(registry._tools)} exploration tools")
    return registry


def main():
    """
    Phase 1 Example: Explore a web page and produce structured knowledge.
    """
    

    url = "https://igethospitality.com"  
    session_id = "phase1_exploration"
    output_file = "exploration_output.json"
    
    # Setup LLM
    logger.info("🤖 Initializing LLM client...")
    llm_config = LLMConfig(
        model_name="llama-3.3-70b-versatile",
        temperature=0.1,  # Lower temperature for more consistent exploration
        max_tokens=8000
    )
    llm = GroqClient(llm_config)
    
    # Setup tools
    logger.info("🛠️  Setting up exploration tools...")
    tool_registry = setup_exploration_tools(session_id)
    
    # Create exploration agent
    logger.info("🤖 Creating page exploration agent...")
    explorer = PageExplorerAgent(
        llm=llm,
        tool_registry=tool_registry,
        max_iterations=15  # Limit iterations to prevent excessive API calls
    )
    
    # Run exploration
    logger.info(f"🌐 Exploring URL: {url}")
    logger.info("-" * 70)
    
    try:
        page_structure = explorer.explore(
            url=url,
            session_id=session_id,
            output_file=output_file
        )
        
        logger.info(f"Output saved to: {output_file}")
        logger.info("\n✅ Phase 1 Exploration Complete!")
        
    except Exception as e:
        logger.error(f"❌ Exploration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
