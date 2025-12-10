from dataclasses import dataclass
import os

@dataclass
class LLMConfig:
    base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1") #api url of the local model
    api_key: str = os.getenv("LLM_API_KEY", "ollama") #just a dummy
    model: str = os.getenv("LLM_MODEL", "deepseek-coder-v2:16b") #this model kinda sucks I'll add a model rotation later

@dataclass
class BrowserConfig:
    headless: bool = False  # for Phase 1, we want visible browser
    default_timeout_ms: int = 20_000
    navigation_timeout_ms: int = 20_000

@dataclass
class ExplorationConfig:
    max_clicks: int = 5
    max_depth: int = 1   # later: multi-step navigation
    capture_screenshot: bool = True
    screenshot_dir: str = "artifacts/screenshots"

llm_config = LLMConfig()
browser_config = BrowserConfig()
exploration_config = ExplorationConfig()
