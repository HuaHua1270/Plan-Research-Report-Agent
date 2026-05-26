from __future__ import annotations

import asyncio
import traceback
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, PrivateAttr

from backend.Agent.src.common.status import Status
from backend.Agent.src.common.web_data import (
    ChildTaskCallback,
    ChildTaskRequest,
    ChildTaskResponse,
)
from backend.Agent.src.service.summarizerService import SummarizerAgentService


class ResearchChildTask(BaseModel):
    task_id: str
    parent_task_id: str
    status: Literal["PENDING", "RUNNING", "DONE", "FAILED"]
    stage: Literal["RESEARCH"] = Status.RESEARCH
    callback_url: str
    input_data: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ResearchTaskManager(BaseModel):
    """Research 子任务管理器。"""

    _tasks: dict[str, ResearchChildTask] = PrivateAttr(default_factory=dict)
    _service: SummarizerAgentService = PrivateAttr(default_factory=SummarizerAgentService)

    async def create_task(self, request: ChildTaskRequest) -> ChildTaskResponse:
        task = ResearchChildTask(
            task_id=request.child_task_id,
            parent_task_id=request.parent_task_id,
            status=Status.PENDING,
            callback_url=request.callback_url,
            input_data=request.input_data,
        )
        self._tasks[task.task_id] = task

        asyncio.create_task(self._execute_task(task.task_id))

        return ChildTaskResponse(
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            status=task.status,
            stage=task.stage,
        )

    async def get_task(self, task_id: str) -> Optional[ResearchChildTask]:
        return self._tasks.get(task_id)

    async def _execute_task(self, task_id: str) -> None:
        task = self._tasks[task_id]
        task.status = Status.RUNNING
        self._tasks[task_id] = task

        try:
            request = ChildTaskRequest(
                parent_task_id=task.parent_task_id,
                child_task_id=task.task_id,
                callback_url=task.callback_url,
                input_data=task.input_data,
            )
            research_json = await self._service.generate_research(request)

            task.status = Status.DONE
            task.result = {"research_json": research_json}
            self._tasks[task_id] = task
        except Exception as exc:
            task.status = Status.FAILED
            task.error = (
                f"research child task {task_id} failed with {type(exc).__name__}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            self._tasks[task_id] = task

        await self._send_callback(task)

    async def _send_callback(self, task: ResearchChildTask) -> None:
        callback = ChildTaskCallback(
            parent_task_id=task.parent_task_id,
            child_task_id=task.task_id,
            stage=task.stage,
            status=task.status if task.status == Status.FAILED else Status.DONE,
            result=task.result,
            error=task.error,
        )
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(task.callback_url, json=callback.model_dump())
            response.raise_for_status()
