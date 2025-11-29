import os
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    GROQ = "groq"
    GEMINI = "gemini"
    OPENAI = "openai"

class LLMConfig(BaseModel):
    """Configuration for LLM providers"""
    
    provider: LLMProvider = Field(default=LLMProvider.GROQ, description="The LLM provider to use")
    
    base_url: Optional[str] = Field( default=None, description="API Base URL (only needed for custom endpoints)")

    model_name: str = Field( default="llama-3.3-70b-versatile", description="model name")
    
    # Common configuration
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Controls randomness in responses. Lower values (e.g., 0.2) make output more focused and deterministic, higher values (e.g., 1.5) make it more creative and varied. Example: 0.0 for factual tasks, 1.0 for creative writing"
    )
    
    top_p: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling parameter. Controls diversity by considering only the top tokens with cumulative probability mass of top_p. Lower values (e.g., 0.1) make output more focused, higher values (e.g., 0.95) allow more diversity. Example: 0.9 for balanced creativity"
    )
    
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum number of tokens to generate in the response. Limits the length of the output. If None, uses model's default limit. Example: 500 for short responses, 2000 for detailed explanations"
    )
    
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="Controls the depth of reasoning for models that support chain-of-thought or reasoning modes (e.g., OpenAI's o1 models). Options typically include 'low', 'medium', 'high'. Higher effort produces more thorough reasoning but takes longer and uses more tokens. Example: 'high' for complex problem-solving, 'low' for simple queries"
    )