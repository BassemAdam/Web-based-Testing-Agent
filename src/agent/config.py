from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class LLMConfig:
    base_url: str = os.getenv("LLM_BASE_URL", "https://api.githubcopilot.com") #api url of the local model
    api_key: str = os.getenv("GITHUB_TOKEN", "") #just a dummy
    model: str = os.getenv("LLM_MODEL", "gpt-5-mini") #default to the current preferred Copilot model

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
