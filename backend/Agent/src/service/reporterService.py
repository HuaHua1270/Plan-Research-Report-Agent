import asyncio
import json

from backend.Agent.src.agent.ReporterAgent import ReportAgent
from backend.Agent.src.agent.enhancement import tool_listener
from backend.Agent.src.common.DTO.Request import ChildTaskRequest
from backend.Agent.src.models import report_llm
from backend.Agent.src.prompts import report_writer_instructions


report_agent = ReportAgent(
    name="ReporterAgent",
    llm=report_llm,
    system_prompt=report_writer_instructions,
    enable_tool_calling=False,
    tool_call_listener=tool_listener,
)


class ReportAgentService:
    """Generate the final report from the plan and per-subtask research summaries."""

    async def generate_report(self, request: ChildTaskRequest) -> str:
        prompt = self._build_prompt(request.input_data)
        report_agent.clear_history()
        return await asyncio.to_thread(report_agent.run, prompt)

    def _build_prompt(self, input_data: dict) -> str:
        research_json = input_data.get("research_json") or {}
        task_summaries = research_json.get("task_summaries") if isinstance(research_json, dict) else None
        summaries_text = (
            self._format_task_summaries(task_summaries)
            if task_summaries
            else json.dumps(research_json, ensure_ascii=False)
        )

        return (
            f"Research topic: {input_data.get('topic', '')}\n"
            f"Language: {input_data.get('language', 'zh')}\n"
            f"Report format: {input_data.get('report_format', 'markdown')}\n"
            "Research plan JSON:\n"
            f"{json.dumps(input_data.get('plan_json'), ensure_ascii=False)}\n\n"
            "Subtask research summaries:\n"
            f"{summaries_text}\n\n"
            "Integrate all subtask summaries into one final structured research report. "
            "Preserve source URLs and organize the report by subtopic."
        )

    def _format_task_summaries(self, task_summaries: list[dict]) -> str:
        sections = []
        for item in task_summaries:
            sections.append(
                f"## {item.get('index', '')}. {item.get('title', '')}\n"
                f"Intent: {item.get('intent', '')}\n"
                f"Query: {item.get('query', '')}\n\n"
                f"{item.get('summary', '')}"
            )
        return "\n\n".join(sections)
