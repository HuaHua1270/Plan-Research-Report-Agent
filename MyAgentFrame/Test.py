import logging

from agent.plan_solve_agent import PlanSolveAgent
from agent.simple_agent import SimpleAgent
from core.Agent import Agent
from core.BaseLLM import BaseChatLLM

logging.basicConfig(level=logging.INFO)

llm = BaseChatLLM(
  model = "deepseek-chat",
  api_key = "sk-ba3d6520a19d45a1b39ff8ccb38cf29b",
  api_base = "https://api.deepseek.com",
  max_tokens=1024,
  temperature=0.8,
  timeout=60
)

agent = SimpleAgent(
    name = "test",
    llm = llm ,
    system_prompt = "You are a helpful assistant.",
    enable_tool_calling = True
)


if __name__ == '__main__':
   responses =  llm.invoke([{"role": "user", "content": "你好"}])
   result = responses.content
   logging.info(result)
   print("Testing...")

