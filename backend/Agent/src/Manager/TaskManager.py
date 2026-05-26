from __future__ import annotations

import uuid
from typing import Optional

import httpx
from pydantic import BaseModel, PrivateAttr

from backend.Agent.src.Manager.Task import ParentTask
from backend.Agent.src.common.status import Status
from backend.Agent.src.common.web_data import (
    ResearchTaskRequest,
    ChildTaskRequest,
    ChildTaskCallback,
)


class TaskManager(BaseModel):
    """中央任务管理器：只管父任务状态机和阶段推进。"""

    _tasks: dict[str, ParentTask] = PrivateAttr(default_factory=dict)

    planner_service_url: str = "http://127.0.0.1:8001"
    research_service_url: str = "http://127.0.0.1:8002"
    reporter_service_url: str = "http://127.0.0.1:8003"
    callback_base_url: str = "http://127.0.0.1:8000"

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    async def create_task(self, req: ResearchTaskRequest) -> ParentTask:
        parent_task_id = req.req_id or self._new_id("research")
        planner_task_id = self._new_id("planner")

        task = ParentTask(
            task_id=parent_task_id,
            status=Status.RUNNING,
            current_stage=Status.PLANNER,
            topic=req.topic,
            language=req.language,
            depth=req.depth,
            max_subtopics=req.max_subtopics,
            need_citations=req.need_citations,
            report_format=req.report_format,
            user_id=req.user_id,
            planner_task_id=planner_task_id,
        )
        self._tasks[parent_task_id] = task

        try:
            await self._create_planner_child(task, req)
        except Exception as exc:
            task.status = Status.FAILED
            task.error = f"failed to create planner task: {exc}"
            self._tasks[parent_task_id] = task
        return task

    async def get_task(self, task_id: str) -> Optional[ParentTask]:
        return self._tasks.get(task_id)

    async def _create_planner_child(self, parent_task: ParentTask, req: ResearchTaskRequest) -> None:
        payload = ChildTaskRequest(
            parent_task_id=parent_task.task_id,
            child_task_id=parent_task.planner_task_id,
            callback_url=f"{self.callback_base_url}/internal/callbacks/planner",
            input_data={
                "topic": req.topic,
                "language": req.language,
                "depth": req.depth,
                "max_subtopics": req.max_subtopics,
                "need_citations": req.need_citations,
                "report_format": req.report_format,
                "user_id": req.user_id,
            },
        )
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.planner_service_url}/planner/tasks", json=payload.model_dump())
            response.raise_for_status()

    async def _create_research_child(self, parent_task: ParentTask) -> None:
        research_task_id = self._new_id("research")
        parent_task.research_task_id = research_task_id
        self._tasks[parent_task.task_id] = parent_task

        payload = ChildTaskRequest(
            parent_task_id=parent_task.task_id,
            child_task_id=research_task_id,
            callback_url=f"{self.callback_base_url}/internal/callbacks/research",
            input_data={
                "plan_json": parent_task.plan_json,
                "topic": parent_task.topic,
                "language": parent_task.language,
                "depth": parent_task.depth,
                "need_citations": parent_task.need_citations,
            },
        )
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.research_service_url}/research/tasks", json=payload.model_dump())
            response.raise_for_status()

    async def _create_report_child(self, parent_task: ParentTask) -> None:
        reporter_task_id = self._new_id("reporter")
        parent_task.reporter_task_id = reporter_task_id
        self._tasks[parent_task.task_id] = parent_task

        payload = ChildTaskRequest(
            parent_task_id=parent_task.task_id,
            child_task_id=reporter_task_id,
            callback_url=f"{self.callback_base_url}/internal/callbacks/reporter",
            input_data={
                "plan_json": parent_task.plan_json,
                "research_json": parent_task.research_json,
                "topic": parent_task.topic,
                "language": parent_task.language,
                "report_format": parent_task.report_format,
            },
        )
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.reporter_service_url}/report/tasks", json=payload.model_dump())
            response.raise_for_status()

    async def handle_planner_callback(self, callback: ChildTaskCallback) -> ParentTask:
        return await self._handle_callback(
            callback=callback,
            expected_stage=Status.PLANNER,
            result_key="plan_json",
            next_stage=Status.RESEARCH,
        )

    async def handle_research_callback(self, callback: ChildTaskCallback) -> ParentTask:
        return await self._handle_callback(
            callback=callback,
            expected_stage=Status.RESEARCH,
            result_key="research_json",
            next_stage=Status.REPORTER,
        )

    async def handle_reporter_callback(self, callback: ChildTaskCallback) -> ParentTask:
        return await self._handle_callback(
            callback=callback,
            expected_stage=Status.REPORTER,
            result_key="report_text",
            next_stage=Status.DONE,
        )

    async def _handle_callback(
        self,
        callback: ChildTaskCallback,
        expected_stage: str,
        result_key: str,
        next_stage: str,
    ) -> ParentTask:
        # 父任务状态更新与验证

        task = self._tasks.get(callback.parent_task_id)
        if task is None:
            raise ValueError(f"parent task not found: {callback.parent_task_id}")

        if task.current_stage != expected_stage:
            return task

        expected_child_task_id = {
            Status.PLANNER: task.planner_task_id,
            Status.RESEARCH: task.research_task_id,
            Status.REPORTER: task.reporter_task_id,
        }[expected_stage]

        if callback.child_task_id != expected_child_task_id:
            return task

        if callback.status == Status.FAILED:
            task.status = Status.FAILED
            task.error = (
                f"{expected_stage} child task {callback.child_task_id} failed: "
                f"{callback.error or f'{expected_stage} failed'}"
            )
            self._tasks[task.task_id] = task
            return task

        if callback.result is None:
            raise ValueError("callback.result is required when status is DONE")


        # 转换到下一个阶段
        # plan -> research
        if result_key == "plan_json":
            task.plan_json = callback.result.get("plan_json", callback.result)
            task.current_stage = next_stage
            self._tasks[task.task_id] = task
            try:
                # 构建下一个阶段的子任务
                await self._create_research_child(task)
            except Exception as exc:
                task.status = Status.FAILED
                task.error = f"failed to create research task: {exc}"
                self._tasks[task.task_id] = task
            return task

        # research -> reporter
        if result_key == "research_json":
            task.research_json = callback.result.get("research_json", callback.result)
            task.current_stage = next_stage
            self._tasks[task.task_id] = task
            try:
                # 构建下一个阶段的子任务
                await self._create_report_child(task)
            except Exception as exc:
                task.status = Status.FAILED
                task.error = f"failed to create reporter task: {exc}"
                self._tasks[task.task_id] = task
            return task

        task.report_text = callback.result.get("report_text", "")
        task.current_stage = next_stage
        task.status = Status.SUCCESS
        self._tasks[task.task_id] = task
        return task
