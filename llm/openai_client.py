import os
from typing import Iterator
from dotenv import load_dotenv
from openai import OpenAI
from .base import LLMClient
from .config import LLMConfig

load_dotenv()

class OpenAIClient(LLMClient):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    def generate(self, messages: [dict[str, str]], tools = None) -> dict:
        """ Main Returned Dict Fields
            - content: The actual text response from the model
            - role: The role of the message sender (usually 'assistant')
            - tool_calls: List of tool calls if the model decided to use a tool
        """
        response = self.client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
            tools=tools
        )
     
        return response.choices[0].message.model_dump()
    
    def stream(self, messages: [dict[str, str]], tools = None) -> Iterator[dict]:
        stream = self.client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
            tools=tools,
            stream=True
        )
        for chunk in stream:
            yield chunk.choices[0].delta.model_dump()
