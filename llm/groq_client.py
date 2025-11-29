import os
from typing import Iterator
from dotenv import load_dotenv
from groq import Groq
from .base import LLMClient
from .config import LLMConfig

# TODO 1: load dotenv
load_dotenv()

class GroqClient(LLMClient):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        # TODO 2: create groq client and set api_key from .env
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    def generate(self, messages: [dict[str, str]], tools = None) -> dict:
        # TODO: write description for Returend Fields 
        """ Main Returned Dict Fields
            - content: The actual text response from the model
            - role: The role of the message sender (usually 'assistant')
            - tool_calls: List of tool calls if the model decided to use a tool
        """
        # TODO 3: call `client.chat.completions.create` with configurations in self.config
        response = self.client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_tokens,
            tools=tools  # TODO 3: now you can pass tools=tools but search about format later when move to tools sections

        )
        # TODO 3: search difference between max_tokens and max_compeletion_tokens
        # max tokens limits number of tokens the model generates in response
        # max completion tokens limits only the generated output. its nwerer and used to eliminate ambiguity
     
        return response.choices[0].message.model_dump()
    
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