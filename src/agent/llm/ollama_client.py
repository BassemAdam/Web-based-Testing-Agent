import os
from openai import OpenAI
from typing import List, Dict, Any, Optional
from ..config import llm_config
from dotenv import load_dotenv
class LLMClient:
    def __init__(self, model: str | None = None, config: Optional[Dict[str, Any]] = None):
        self.client = OpenAI(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key
        )
        self.model = model or llm_config.model

        # Defaults preserve previous behavior unless overridden per-instance.
        self._default_max_tokens: int = 256
        self._default_temperature: float = 0.2
        self._default_ollama_options: Dict[str, Any] = {}

        if config:
            if "max_tokens" in config and config["max_tokens"] is not None:
                self._default_max_tokens = int(config["max_tokens"])
            if "temperature" in config and config["temperature"] is not None:
                self._default_temperature = float(config["temperature"])

            # Convenience keys for common Ollama options.
            if config.get("num_ctx") is not None:
                self._default_ollama_options["num_ctx"] = int(config["num_ctx"])
            if config.get("num_predict") is not None:
                self._default_ollama_options["num_predict"] = int(config["num_predict"])

            # Allow arbitrary extra Ollama options.
            extra_options = config.get("options")
            if isinstance(extra_options, dict):
                self._default_ollama_options.update(extra_options)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        options: Dict[str, Any] | None = None,
    ) -> str:
        resolved_max_tokens = max_tokens if max_tokens is not None else self._default_max_tokens
        resolved_temperature = temperature if temperature is not None else self._default_temperature

        # Ollama OpenAI-compatible endpoint supports passing native options via `extra_body`.
        ollama_options: Dict[str, Any] = dict(self._default_ollama_options)
        if num_ctx is not None:
            ollama_options["num_ctx"] = int(num_ctx)
        if num_predict is not None:
            ollama_options["num_predict"] = int(num_predict)
        if options:
            ollama_options.update(options)

        create_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": resolved_max_tokens,
            "temperature": resolved_temperature,
        }
        if ollama_options:
            create_kwargs["extra_body"] = {"options": ollama_options}

        resp = self.client.chat.completions.create(**create_kwargs)
        return resp.choices[0].message.content.strip()

class CopilotClient:
    """
    LLM Client using GitHub Copilot API (OpenAI-compatible).
    """
    
    def __init__(self, model: str = "gpt-4o", config: Dict[str, Any] = None):
        self.model = model
        self.config = config or {}
        load_dotenv()
        print("===========================================================")
        print(os.getenv("GITHUB_TOKEN"))
        # GitHub Copilot uses OpenAI-compatible API
        self.client = OpenAI(
            api_key=os.getenv("GITHUB_TOKEN"),
            base_url="https://api.githubcopilot.com"
        )
    
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Send a chat completion request."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.config.get("temperature", 0.2),
            max_tokens=self.config.get("max_tokens", 4096)
        )
        return response.choices[0].message.content
