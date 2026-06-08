import asyncio
import json
from typing import Any

from MyAgentFrame.core.config import Config
from MyAgentFrame.tool.registry import ToolRegistry
from backend.Agent.src.agent.SummarizerAgent import SummarizerAgent
from backend.Agent.src.agent.enhancement import tool_listener
from backend.Agent.src.common.DTO.Request import ChildTaskRequest
from backend.Agent.src.models import summarize_llm
from backend.Agent.src.prompts import task_summarizer_instructions
from backend.Agent.src.tools.SearchTool import SearchTool


research_config = Config(
    subagent_enabled=False,
    todowrite_enabled=False,
    devlog_enabled=False,
)

summarize_agent = SummarizerAgent(
    name="SummarizerAgent",
    llm=summarize_llm,
    system_prompt=task_summarizer_instructions,
    enable_tool_calling=True,
    tool_call_listener=tool_listener,
    tool_registry=ToolRegistry(),
    config=research_config,
)

search_tool = SearchTool()
summarize_agent.tool_registry.register_tool(search_tool)


class SummarizerAgentService:
    """Research LLM service: run tool-assisted research from a plan."""

    async def generate_research(self, request: ChildTaskRequest) -> dict[str, Any]:
        input_data = request.input_data
        plan_json = input_data.get("plan_json") or {}
        if isinstance(input_data.get("subtopic"), dict):
            subtopic = input_data["subtopic"]
            index = int(input_data.get("subtopic_index") or 1)
            total = int(input_data.get("subtopic_total") or 1)
            prompt = self._build_subtopic_prompt(input_data, subtopic, index, total)
            summarize_agent.clear_history()
            summary = await asyncio.to_thread(summarize_agent.run, prompt)
            return {
                "index": index,
                "title": subtopic.get("title", f"Subtopic {index}"),
                "intent": subtopic.get("intent", ""),
                "query": subtopic.get("query", ""),
                "summary": summary,
                "plan_json": plan_json,
            }

        subtopics = self._extract_subtopics(plan_json)
        task_summaries = []

        # 拿出子任务 并执行
        for index, subtopic in enumerate(subtopics, start=1):
            prompt = self._build_subtopic_prompt(input_data, subtopic, index, len(subtopics))
            summarize_agent.clear_history()
            summary = await asyncio.to_thread(summarize_agent.run, prompt)
            task_summaries.append(
                {
                    "index": index,
                    "title": subtopic.get("title", f"Subtopic {index}"),
                    "intent": subtopic.get("intent", ""),
                    "query": subtopic.get("query", ""),
                    "summary": summary,
                }
            )

        return {
            "task_summaries": task_summaries,
            "summary": self._join_summaries(task_summaries),
            "plan_json": plan_json,
        }

    def _extract_subtopics(self, plan_json: Any) -> list[dict[str, Any]]:
        if isinstance(plan_json, dict):
            raw_subtopics = plan_json.get("subtopics")
        elif isinstance(plan_json, list):
            raw_subtopics = plan_json
        else:
            raw_subtopics = None

        if not isinstance(raw_subtopics, list) or not raw_subtopics:
            raise ValueError("research input plan_json must contain a non-empty subtopics list")

        subtopics: list[dict[str, Any]] = []
        for index, item in enumerate(raw_subtopics, start=1):
            if isinstance(item, dict):
                title = str(item.get("title") or f"Subtopic {index}")
                intent = str(item.get("intent") or "")
                query = str(item.get("query") or title)
            else:
                title = str(item)
                intent = ""
                query = title
            subtopics.append({"title": title, "intent": intent, "query": query})
        return subtopics

    def _build_subtopic_prompt(
        self,
        input_data: dict[str, Any],
        subtopic: dict[str, Any],
        index: int,
        total: int,
    ) -> str:
        return (
            f"Research topic: {input_data.get('topic', '')}\n"
            f"Language: {input_data.get('language', 'zh')}\n"
            f"Depth: {input_data.get('depth', 'standard')}\n"
            f"Need citations: {input_data.get('need_citations', True)}\n"
            f"Subtask: {index}/{total}\n"
            f"Subtask title: {subtopic.get('title', '')}\n"
            f"Subtask intent: {subtopic.get('intent', '')}\n"
            f"Search query: {subtopic.get('query', '')}\n\n"
            "Use the Search tool when useful. Return one focused Markdown summary for this subtask. "
            "Include key findings, useful facts, and source URLs when available."
        )

    def _join_summaries(self, task_summaries: list[dict[str, Any]]) -> str:
        sections = []
        for item in task_summaries:
            sections.append(
                f"## {item['index']}. {item['title']}\n\n"
                f"Intent: {item.get('intent', '')}\n\n"
                f"Query: {item.get('query', '')}\n\n"
                f"{item.get('summary', '')}"
            )
        return "\n\n".join(sections)
