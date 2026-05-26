import os

from MyAgentFrame.core import BaseChatLLM


def _build_llm() -> BaseChatLLM:
    return BaseChatLLM(
        model='deepseek-chat',
        api_key='sk-ba3d6520a19d45a1b39ff8ccb38cf29b',
        api_base='https://api.deepseek.com',
        max_tokens=2048,
        temperature=0.6,
        timeout=60,
    )

   #  model='deepseek-chat',
   #  api_key='sk-ba3d6520a19d45a1b39ff8ccb38cf29b',
   #  base_url='https://api.deepseek.com',
   #  max_tokens=2048,
   #  temperature=0.6
plan_llm = _build_llm()
report_llm = _build_llm()
summarize_llm = _build_llm()

