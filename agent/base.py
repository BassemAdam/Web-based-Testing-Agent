from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field
from loguru import logger
import json

# Optional langfuse for tracing
try:
    from langfuse import observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    # Create a no-op decorator
    def observe(**kwargs):
        def decorator(func):
            return func
        return decorator

from llm.base import LLMClient
from tools.registry import ToolRegistry


class BaseAgentState(BaseModel):
    """
    Holds the evolving state of an agent's execution.
    """
    messages: list[dict] = Field(default_factory=list)
    is_finished: bool = False
    iteration: int = 0

    def add_message(self, role: str, content: str, **extra):
        msg = {"role": role, "content": content}
        # Only add extra fields if they have non-None values
        for key, value in extra.items():
            if value is not None:
                msg[key] = value
        self.messages.append(msg)
        

class Agent(ABC):
    def __init__( self, llm: LLMClient, tool_registry: ToolRegistry, max_iterations: int = 100):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        # initial state to start with
        self.inital_state = BaseAgentState()

    @abstractmethod
    def start_point(self, *args, **kwargs) -> BaseAgentState:
        """ Start Point of State for example start of user query or anything """
        raise NotImplementedError()
    
    @abstractmethod
    def run(self, state: BaseAgentState) -> BaseAgentState:
        """ Run 1 Step/Iteration """
        raise NotImplementedError()

    def iterate(self, *args, **kwargs) -> BaseAgentState:
        state = self.start_point(*args, **kwargs)
        # TODO: iteration schema alwayse same regarding `self.run(state)``
        # TODO: istate.is_finished or state.iteration > self.max_iteration
        # TODO: while: run()
        while not state.is_finished and state.iteration < self.max_iterations:
            state = self.run(state)
            state.iteration += 1

        return state

    # LLM WRAPPER
    @observe(name="llm-call", as_type="generation")
    def llm_generate(self, state: BaseAgentState, tools: list = None):
        # TODO: wrap code to generate from llm -- self.tool_registry.to_client_tools to convert to client format
        try:
            if tools is None:
                tools = self.tool_registry.to_client_tools(self.llm.config.provider)
            
            response = self.llm.generate(state.messages, tools=tools)
            return response
        except Exception as error:
            logger.error(f"LLM API error: {error}")
            # Return error as content so agent can handle it
            return {
                "content": f"LLM API Error: {str(error)}. Please use only the tools provided with their exact names.",
                "tool_calls": None
            }
    # TOOL EXECUTION WRAPPER
    @observe(name="tool-call", as_type="tool")
    def call_tool(self, tool_call):
        # TODO: wrap code to execute function with error pron and tracing here
        try:
            func_name = tool_call["function"]["name"]
            args_raw = tool_call["function"]["arguments"]
            
            if isinstance(args_raw, str):
                func_inputs = json.loads(args_raw)
            else:
                func_inputs = args_raw
            
            # Get the tool and execute it
            tool = self.tool_registry.get(func_name)
            func_results = tool(**func_inputs)
            
            return {
                "role": "tool",
                "tool_call_id": tool_call.get("id"),
                "content": json.dumps(func_results),
            }
        except Exception as error:
            logger.error(f"Tool execution error: {error}")
            return {
                "role": "tool",
                "tool_call_id": tool_call.get("id"),
                "content": json.dumps({"error": str(error)}),
            }