import asyncio
import json
import re
from datetime import date
from typing import Any

from backend.Agent.src.agent.PlannerAgent import PlanAgent
from backend.Agent.src.agent.enhancement import tool_listener
from backend.Agent.src.common.web_data import ChildTaskRequest
from backend.Agent.src.models import plan_llm
from backend.Agent.src.prompts import todo_planner_instructions


plan_agent = PlanAgent(
    name="PlannerAgent",
    llm=plan_llm,
    system_prompt=todo_planner_instructions,
    enable_tool_calling=False,
    tool_call_listener=tool_listener,

)


class PlannerAgentService:
    """Planner LLM 服务：负责把研究主题拆成结构化计划。"""

    async def generate_plan(self, request: ChildTaskRequest) -> dict[str, Any]:
        input_data = request.input_data
        prompt = self._build_prompt(input_data)

        raw_text = await asyncio.to_thread(plan_agent.run, prompt)
        return self._parse_plan(raw_text)


    def _build_prompt(self, input_data: dict[str, Any]) -> str:
        return (
            f"当前日期：{date.today().isoformat()}\n"
            f"研究主题：{input_data['topic']}\n"
            f"报告语言：{input_data.get('language', 'zh')}\n"
            f"研究深度：{input_data.get('depth', 'standard')}\n"
            f"最多子主题数：{input_data.get('max_subtopics', 5)}\n"
            f"是否需要引用：{input_data.get('need_citations', True)}\n"
            "请根据系统要求生成研究计划。"
        )

    def _parse_plan(self, raw_text: str) -> dict[str, Any]:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if not match:
                raise ValueError(f"planner returned non-json content: {raw_text}")
            data = json.loads(match.group(0))

        if isinstance(data, list):
            data = {"subtopics": data}

        subtopics = data.get("subtopics")
        if not isinstance(subtopics, list) or not subtopics:
            raise ValueError("planner result must contain non-empty subtopics")

        return data

