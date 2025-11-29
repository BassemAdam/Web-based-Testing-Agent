# GenAI Lab - Autonomous Testing Agent

## 🎯 Project Overview

This project implements an **Autonomous Testing Agent** that can understand and test web applications using AI. The agent explores web pages, understands their structure and behavior, and generates comprehensive test cases.

## 🚀 Phase 1: Exploration & Knowledge Acquisition (CURRENT)

### Goal
The Agent ingests a URL and obtains deep understanding of the page's structure, logic, and interactivity.

### How the Agent "Sees" - Hybrid Approach

The agent uses a **hybrid exploration strategy** combining three complementary approaches:

1. **DOM Analysis** 📋
   - Extracts hierarchical structure of HTML elements
   - Identifies semantic roles using accessibility tree
   - Detects interactive elements (buttons, forms, inputs)
   - Analyzes attributes and properties

2. **Visual Analysis** 👁️
   - Captures full-page and element-specific screenshots
   - Analyzes visual layout and positioning
   - Detects visual groupings and hierarchies
   - Creates visual signatures for self-healing

3. **Interactive Exploration** 🔍
   - Detects hover effects and dropdowns
   - Identifies dynamic content loading
   - Discovers multi-step interaction flows
   - Tests element behaviors safely

### Exploration Tools

#### DOM Extraction Tools (`exploration/dom_tools.py`)
- `extract_dom_tree` - Get structured DOM with attributes
- `extract_interactive_elements` - Find all clickable/fillable elements
- `extract_accessibility_tree` - Get semantic structure
- `detect_page_sections` - Identify logical sections (header, nav, etc.)
- `detect_technologies` - Identify frameworks (React, Vue, etc.)

#### Visual Analysis Tools (`exploration/visual_tools.py`)
- `take_full_page_screenshot` - Capture entire page visually
- `take_element_screenshot` - Screenshot specific elements
- `extract_visual_layout` - Get positions, colors, styling
- `detect_visual_groups` - Find visually related elements
- `analyze_element_visibility` - Check true visibility

#### Interactive Exploration Tools (`exploration/interactive_tools.py`)
- `explore_clickable_elements` - Find and classify clickable items
- `detect_dynamic_content` - Identify AJAX/dynamic loading
- `detect_interaction_flows` - Find login, search, checkout flows
- `explore_hover_effects` - Detect dropdowns and tooltips
- `test_interactive_element` - Safely test element behavior

### Output: Structured Page Representation

The agent produces a `PageStructure` object containing:

```python
PageStructure(
    url="...",
    page_title="...",
    exploration_timestamp="...",
    
    # Core Data
    elements=[ElementCandidate(...)],      # All interactive elements
    sections=[PageSection(...)],            # Logical page sections
    flows=[InteractionFlow(...)],           # Multi-step interactions
    
    # Visual & Metadata
    full_page_screenshot="base64...",
    accessibility_tree={...},
    technologies_detected=["React", "Bootstrap"],
    
    # Statistics
    total_elements_found=45,
    exploration_depth=12
)
```

#### ElementCandidate - Self-Healing Capable

Each element includes:
- **Multiple Locator Strategies**: ID, CSS, XPath, text, role, ARIA labels
- **Semantic Information**: Description, role, context
- **Visual Signature**: Screenshot, bounding box, visible text
- **Interaction Capabilities**: Expected actions (click, fill, etc.)
- **Initial State**: Attributes, values, checked status

This redundancy enables **self-healing** - if one locator breaks, others can still find the element.

### 📊 Example Output

See `exploration_output.json` after running for complete structured output.

## 🛠️ Setup & Installation

### 1. Initialize UV Environment

```bash
# Install UV
pip install uv

# Sync dependencies
uv sync

# Activate environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

### 2. Install Playwright Browsers

```bash
playwright install chromium
```

### 3. Setup Environment Variables

Create `.env` file:
```
GROQ_API_KEY=your_groq_api_key_here
```

Get your Groq API key from: https://console.groq.com/

## 🎮 Running Phase 1

### Basic Usage

```bash
python main.py
```

This will:
1. Navigate to the configured URL (default: playwright.dev)
2. Systematically explore using all tools
3. Build structured representation
4. Save to `exploration_output.json`

### Customize Exploration

Edit `main.py` to change:
```python
url = "https://your-target-website.com"  # URL to explore
session_id = "my_session"                # Session identifier
output_file = "my_output.json"           # Output filename
max_iterations = 15                      # Exploration depth
```

### Programmatic Usage

```python
from exploration.agent import PageExplorerAgent
from llm.groq_client import GroqClient
from llm.config import LLMConfig
from tools.registry import ToolRegistry

# Setup
llm = GroqClient(LLMConfig(model_name="llama-3.3-70b-versatile"))
tools = setup_exploration_tools()  # See main.py
explorer = PageExplorerAgent(llm, tools)

# Explore
page_structure = explorer.explore(
    url="https://example.com",
    output_file="output.json"
)

# Access results
print(f"Found {page_structure.total_elements_found} elements")
for element in page_structure.elements:
    print(f"{element.element_type}: {element.description}")
```

## 📁 Project Structure

```
exploration/              # Phase 1 implementation ⭐
  ├── __init__.py
  ├── models.py          # PageStructure, ElementCandidate, etc.
  ├── agent.py           # PageExplorerAgent
  ├── dom_tools.py       # DOM extraction tools (5 tools)
  ├── visual_tools.py    # Visual analysis tools (5 tools)
  └── interactive_tools.py # Interactive exploration tools (5 tools)

agent/                   # Agent framework
  └── base.py           # Base Agent class (used by exploration)

llm/                     # LLM clients
  ├── base.py
  ├── config.py
  ├── groq_client.py
  └── openai_client.py

tools/                   # Tool framework
  ├── base.py
  ├── decorator.py
  ├── registry.py
  └── toolkit/
      └── web_explorer.py  # Basic web navigation tools

browser_manager.py       # Playwright browser lifecycle
session.py              # Session management
main.py                 # Phase 1 full example
demo_phase1.py          # Phase 1 quick demo

# Documentation
README.md               # This file - complete guide
QUICKSTART.md          # 5-minute start guide  
ARCHITECTURE.md        # Technical deep dive
DIAGRAMS.md            # Visual flow diagrams
OVERVIEW.md            # Quick reference
```

## 🎓 Key Concepts

### Agent-Based Exploration

The `PageExplorerAgent` autonomously decides:
- Which tools to use and when
- What information to gather
- When exploration is complete

It uses an LLM to make intelligent decisions rather than following rigid scripts.

### Tool-Based Architecture

Tools are modular functions that:
- Have clear descriptions (for LLM understanding)
- Accept typed parameters
- Return structured data
- Can be composed by the agent

### Multi-Strategy Locators

Each element gets multiple locators:
```python
{
  "id": "#login-button",
  "css": "form > button.primary",
  "text": "Sign In",
  "role": "button",
  "aria": "[aria-label='Login']"
}
```

If the page changes and one breaks, others may still work (self-healing).

## 🔜 Next Phases

### Phase 2: Test Case Generation
- Use PageStructure to generate comprehensive tests
- Create test scenarios for each flow
- Generate assertions based on expected behavior

### Phase 3: Test Execution & Validation
- Execute generated tests
- Validate results
- Report failures

### Phase 4: Self-Healing & Maintenance
- Detect when tests break due to UI changes
- Use visual signatures to relocate elements
- Automatically update locators

## 📚 References

### Original Lab References
[HuggingFace Agent Course](https://huggingface.co/learn/agents-course/en/unit0/introduction)

### Context Engineering
* [How Long Contexts Fail](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)
* [Context Engineering by Langchain](https://blog.langchain.com/context-engineering-for-agents/)

### Multi-Agent Systems
* [Conceptual Guide: Multi Agent Architectures](https://www.youtube.com/watch?v=4nZl32FwU-o)
* [Advanced Context Engineering for Agents](https://www.youtube.com/watch?v=IS_y40zY-hc)

## 💡 Creative Decisions & Design Choices

### Why Hybrid Approach?

1. **DOM alone is insufficient** - Doesn't capture visual layout or dynamic behavior
2. **Visual alone is expensive** - Screenshots consume tokens and need vision models
3. **Hybrid is optimal** - DOM provides structure, visuals provide context, interaction reveals behavior

### Why Multiple Locators?

Real-world web apps change frequently. Multiple locator strategies provide:
- **Robustness** - Backup if primary locator breaks
- **Self-healing** - Can automatically try alternatives
- **Context** - Different locators capture different aspects

### Why Agent-Based?

Traditional web scrapers follow rigid scripts. An agent:
- **Adapts** to different page structures
- **Discovers** unexpected elements
- **Prioritizes** important interactions
- **Decides** when exploration is sufficient

## 🐛 Troubleshooting

### "Module not found" errors
```bash
uv sync
```

### "Browser not found" errors
```bash
playwright install chromium
```

### API rate limits
- Reduce `max_iterations` in main.py
- Use cheaper/faster model
- Add delays between tool calls

### Exploration incomplete
- Increase `max_iterations`
- Check LLM is responding with tool calls
- Review logs for errors

---

**Status**: ✅ Phase 1 Complete - Exploration & Knowledge Acquisition Implemented

## TODOs

### 1. Initalize your uv environment

if you want to start from scratch
```bash
pip install uv

uv init --python 3.11
uv add pandas groq dotenv
uv sync
# in linux
source .venv/bin/activate
# in windows
.venv\Scripts\activate
```

since I already initalized and downloaded library you can start from `uv sync`

to add new library
```bash
uv add ...
# or 
uv pip install ...
```

### 2. Create Simple LLM Client
1. go to file `llm/config.py` - add fields to `LLMConfig(BaseModel)` will find TODOs and description of some fields -- be creative add whatever you feel like
2. go create groq account and get your api key then added .env under `GROQ_API_KEY` or whatever you want
3. read `llm/base.py` then go create your first client at `llm/groq_client.py`

### 2.1 Extra
- instead of just return dict in `client.generate` or `client.stream` should return List of Messages
1. create new folder messages
2. create base Message(BaseModel)
3. inherit different messages(HumanMessage, AIMessage, ToolMessage, ThinkingMessage)
- why do we need it ?
    - different clients/models have different names for "role"
        - like for Groq it's "user" but for other is "human"
        - like for Groq it's "reasoning" but for other is "thinking"
        etc...
    - so we need to parse it and handle it differently depend on model
4. update llm/base and llm/groq_client to use those
    
### 3. Session and BrowserManager
before tools

since we will need tools to control Browser Page or code 
we need some Browser Manager that open one page foreach session with an agent
thus there's some file you can check and read before navigating to the next section
1. `session.py` allow us to write code like this
    there's small TODO there to initate session_id if not passed 
    ```python
    with Session() as session:
        print(session.session_id)
    ```
2. `browser_manager.py` manage session page
for each session there's one page agent agent can control
to get the page = get_page()

### 4. Create Simple Tool Manager
A tool should have 4 components
    - A textual description of what the function does.
    - A Callable (something to perform an action).
    - Arguments with typings.
    - (Optional) Outputs with typings.
    + session_id: (only since we need it)
    
This module help to convert simple function that already have the 4 components to Tool we can add to our prompt later
```py
def calculator(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b
``` 
```text
Tool Name: calculator, Description: Multiply two integers., Arguments: a: int, b: int, Outputs: int
```

allow us to create registery for our tools

1. go to the `tools/base.py` and compelete TODOs
    this will create the base for later
2. go to the `tools/decorator.py` and compelete TODOs
    now we can write
    ```py
    @tool()
    def calculator(a: int, b: int) -> int:
        """Multiply two integers."""
        return a * b
    # get description of tool
    print(calculator.to_string())
    # call tool
    print(calculator(2, 3))
    ``` 
    > see more examples in `tools/toolkit/builtin`
3. TODO implement simple builtin tools
    - to check if json is valid inside `json_tools.py`
        > Why do we need it? 
        > answer:
    - file tools `file_tools.py`
    - code tools `code_tools.py`

4. now after you familiarized with basic tools lets create more advance tools that will help us in our project
    go implement TODOs `tools/toolkit/web_explorer.py` it should use `get_page(session_id)` from `browser_manager`

5. run and make sure everything works correctly
```bash
python -m tools.main
```

### 5.1. MiniAgents - Raw First Agent (Unit Tester)
let's build agent from scratch using `tools`, `llm`
```
the agents have some `tools` 
inputs:
    - files_under_test: list[str]
    - directory_output_file: str
```
the agent generate unit tests using pytest and test them and gets results

**TODOs** inside `agent/examples/00_raw_unit_tester.py`
```bash
python -m agent.examples.00_raw_unit_tester
```
**Extras TODOs** 
- add langfuse to `llm/base`
- inside `agent/examples/01_raw_traced_unit_tester.py` there will be example on how to use langfuse
- get your api keys for langfuse and try run it
    ```bash
    python -m agent.examples.01_raw_traced_unit_tester
    ```
- the expected output
    ![langfuse](assets/langfuse.png)


### 5.2. MiniAgents library (base)
let's build framework for agents after we experiement with it 

go to `agent/base.py` fill free to change it add to it or remove it -- as I added before implementing examples above --


### Notes Before Next TODOs
* If you try to increase the number of files to test --> you'll start to see slowness in generation or may hit MaxTokensPerDay or MaxTokensPerMinute.
* Why does this happen? -> because the context of all messages and tool history is kept, whether we need it or not.
    * For example: the agent needs to list all files in the current directory (depth 2) to know which directory to use.
    * All files are kept in context, and every time we run a new iteration, it digests them again + other extra accumulated knowledge.

* Solutions
    * maybe we run one file at a time
    * maybe we make the `llm` summarize the data or what it needs later in a scratchpad (`small memory`)
    * instead of summarizing, we can make the `llm` write to a DB and retrieve what it needs later, for example:
        ```
        iter 1:
            llm -> write:
                directory_i_am_in = ...
                directory_root_files = ...

        iter 2:
            ...

        iter 3:
            ...

        iter n:
            llm -> retrieve directory_i_am_in
        ```

### 5.3 MiniAgents library (UnitTesterAgent)
just the implementation of `agent/examples/01_raw_traced_unit_tester.py` written from the `Agent` class
and run
```bash
python -m agent.examples.02_use_v1_agent
```
### 5.4 MiniAgents library (UnitTesterAgentv2)
    let's improve it by allowing make agent output what it needs only in <scratchpad>

    and prune the output tools later

    llm -> ToolCall_1 -> Summarize -> prune ToolCall_1 from context -> ToolCall_2 -> ....

change State by override new one and add scratchpad -> and remove old messages
and run
```bash
python -m agent.examples.03_use_v2_agent
```
### 5.5 MiniAgents library 
TO BE CONTINUED 😈
