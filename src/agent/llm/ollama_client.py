from openai import OpenAI
from typing import List, Dict
from ..config import llm_config

class LLMClient:
    def __init__(self, model: str | None = None):
        self.client = OpenAI(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key
        )
        self.model = model or llm_config.model

    def chat(self, messages: List[Dict], max_tokens: int = 256, temperature: float = 0.2) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
