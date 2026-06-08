from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, TypeAlias

from backend.Agent.src.common.DO.Task import (
    ParentTask,
    PlannerChildTask,
    ReportChildTask,
    ResearchChildTask,
)
from backend.Agent.src.common.DTO.Request import ResearchTaskRequest
from backend.Agent.src.common.status import Status


ChildTask: TypeAlias = PlannerChildTask | ResearchChildTask | ReportChildTask


@dataclass(frozen=True)
class QueueJob:
    queue_name: str
    payload: dict[str, Any]


class TaskFactory:
    """Build task objects and lightweight queue jobs without side effects."""

    def build_parent_task(self, req: ResearchTaskRequest) -> ParentTask:
        if not req.topic:
            raise ValueError("topic is required")

        return ParentTask(
            task_id=req.req_id or self.new_id("research"),
            status=Status.RUNNING.value,
            current_stage=Status.PLANNER.value,
            topic=req.topic,
            language=req.language,
            depth=req.depth,
            max_subtopics=req.max_subtopics,
            need_citations=req.need_citations,
            report_format=req.report_format,
            user_id=req.user_id,
            planner_task_id=self.new_id("planner"),
        )

    def build_planner_child_task(self, parent: ParentTask) -> PlannerChildTask:
        if not parent.planner_task_id:
            raise ValueError("planner_task_id is required")

        return PlannerChildTask(
            task_id=parent.planner_task_id,
            parent_task_id=parent.task_id,
            status=Status.PENDING.value,
            stage=Status.PLANNER.value,
            input_data={
                "topic": parent.topic,
                "language": parent.language,
                "depth": parent.depth,
                "max_subtopics": parent.max_subtopics,
                "need_citations": parent.need_citations,
                "report_format": parent.report_format,
                "user_id": parent.user_id,
            },
        )

    def build_research_child_task(
        self,
        parent: ParentTask,
        *,
        task_id: str | None = None,
        subtopic: dict[str, Any] | None = None,
        subtopic_index: int | None = None,
        subtopic_total: int | None = None,
        plan_json: dict[str, Any] | list[Any] | None = None,
    ) -> ResearchChildTask:
        task_id = task_id or parent.research_task_id or self.new_id("research")
        input_data: dict[str, Any] = {
            "plan_json": plan_json if plan_json is not None else parent.plan_json,
            "topic": parent.topic,
            "language": parent.language,
            "depth": parent.depth,
            "need_citations": parent.need_citations,
        }
        if subtopic is not None:
            input_data["subtopic"] = subtopic
        if subtopic_index is not None:
            input_data["subtopic_index"] = subtopic_index
        if subtopic_total is not None:
            input_data["subtopic_total"] = subtopic_total

        return ResearchChildTask(
            task_id=task_id,
            parent_task_id=parent.task_id,
            status=Status.PENDING.value,
            stage=Status.RESEARCH.value,
            input_data=input_data,
        )

    def build_report_child_task(self, parent: ParentTask, *, task_id: str | None = None) -> ReportChildTask:
        task_id = task_id or parent.reporter_task_id or self.new_id("reporter")

        return ReportChildTask(
            task_id=task_id,
            parent_task_id=parent.task_id,
            status=Status.PENDING.value,
            stage=Status.REPORTER.value,
            input_data={
                "plan_json": parent.plan_json,
                "research_json": parent.research_json,
                "topic": parent.topic,
                "language": parent.language,
                "report_format": parent.report_format,
            },
        )

    def build_queue_job(self, child_task: ChildTask, queue_name: str) -> QueueJob:
        return QueueJob(
            queue_name=queue_name,
            payload={"child_task_id": child_task.task_id},
        )

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"
