import os
import time
from typing import Iterator
from dotenv import load_dotenv
from groq import Groq, RateLimitError, BadRequestError
from loguru import logger
from .base import LLMClient
from .config import LLMConfig

# TODO 1: load dotenv
load_dotenv()

class GroqClient(LLMClient):
    # List of fallback models to try when rate limit is reached
    FALLBACK_MODELS = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3-32b",
        "groq/compound",
        "groq/compound-mini",
        "moonshotai/kimi-k2-instruct-0905",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        # Use base_url from config if available (supports proxies/custom gateways)
        self.client = Groq(
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url=config.base_url if config.base_url else None
        )
        # Keep track of the currently active model to avoid retrying failed models
        self.active_model = config.model_name
    
    def generate(self, messages: [dict[str, str]], tools = None) -> dict:
        # TODO: write description for Returend Fields 
        """ Main Returned Dict Fields
            - content: The actual text response from the model
            - role: The role of the message sender (usually 'assistant')
            - tool_calls: List of tool calls if the model decided to use a tool
        """
        
        # Construct the list of models to try, starting with the active model
        # This ensures we stick to a working fallback model if the primary one failed previously
        models_to_try = [self.active_model] + [m for m in self.FALLBACK_MODELS if m != self.active_model]
        
        # Ensure the primary config model is also in the list if it's not the active one
        if self.config.model_name not in models_to_try:
             models_to_try.append(self.config.model_name)
        
        for model in models_to_try:
            try:
                # logger.debug(f"Attempting generation with model: {model}")
                
                # TODO 3: call `client.chat.completions.create` with configurations in self.config
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=self.config.temperature,
                    top_p=self.config.top_p,
                    max_tokens=self.config.max_tokens,
                    tools=tools 
                )
                
                # If successful, update the active model so we use it next time
                if model != self.active_model:
                    logger.info(f"Switched active model to: {model}")
                    self.active_model = model
             
                return response.choices[0].message.model_dump()
            
            except RateLimitError as e:
                logger.warning(f"Rate limit reached for model {model}. Switching to next model...")
                continue
            except BadRequestError as e:
                if "model_decommissioned" in str(e) or "404" in str(e) or "not found" in str(e).lower():
                    logger.warning(f"Model {model} is unavailable (decommissioned/not found). Switching to next model...")
                    continue
                raise e
            except Exception as e:
                # If it's a 429 error but not caught as RateLimitError for some reason
                if "429" in str(e) or "rate_limit_exceeded" in str(e):
                    logger.warning(f"Rate limit (generic) reached for model {model}. Switching to next model...")
                    continue
                if "model_decommissioned" in str(e):
                    logger.warning(f"Model {model} is decommissioned. Switching to next model...")
                    continue
                raise e
        
        # If we get here, all models failed
        raise Exception("All models failed due to rate limits or errors.")
    
    def stream(self, messages: [dict[str, str]], tools = None) -> Iterator[dict]:
        # TODO 3: call `client.chat.completions.create` with stream options configurations in self.config
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
                
                
if __name__ == "__main__":
    #TODO: initlaize configuraiton with reasoning model -- search for groq reasoning models 
    config = LLMConfig(model_name="llama-3.3-70b-versatile")
    client = GroqClient(config)
    
    #TODO: write messages with (1. system prompt on how the model is QA engineer and know python, playwright etc... provide in course) 
    #TODO: (2. Ask model to "write a plan to build a software autonomus like cursor but for testing") 
    messages = [
        {
            "role": "system", "content": """You are an expert QA Automation Engineer. 
            You have extensive knowledge of Python, Playwright, Selenium, and software testing best practices.
            You are capable of designing autonomous testing agents.""",
        },
        {
            "role": "user", "content": "write a plan to build a software autonomus like cursor but for testing"   
        }
    ]
    
    #TODO: test client.generate
    print("--- Generating Response ---")
    response = client.generate(messages)
    print(response['content'])
    
    #TODO: test client.stream and mention what's difference and why we need it?
    # YOUR_ANSWER: ...
    # Difference: Stream returns chunks of the response as they are generated, rather than waiting for the full response.
    # Why we need it: It improves user experience by reducing perceived latency (Time to First Token).
    
    print("\n--- Streaming Response ---")
    for chunk in client.stream(messages):
        print(chunk)
    
    #TODO add the new answer to messages -> create multi-turn conversation (with same system message from above)
        # user: your name is CHATTAH tester
        # assisstant: ...
        # user: tell me what's your name and what are language you expert in it ?
    messages = [
        messages[0],
        {"role": "user", "content": "your name is CHATTAH tester"},        
    ]
    # TODO: first turn -> get answer -> print answer -> append answer to messages "i.e state"
    response = client.generate(messages)
    answer = response['content']
    print(f"Assistant: {answer}")
    messages.append({"role": "assistant", "content": answer})
    
    # TODO: second turn -> get answer -> print answer -> append answer to messages "i.e state"
    new_message = {"role": "user", "content": "tell me what's your name and what are language you expert in it ?"}
    messages.append(new_message)
    response = client.generate(messages)
    answer = response['content']
    print(f"Assistant: {answer}")
    messages.append({"role": "assistant", "content": answer})