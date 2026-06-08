from __future__ import annotations

import asyncio
import json
import traceback
from typing import Optional

from pydantic import PrivateAttr

from backend.Agent.src.common.DO.Task import ParentTask, ReportChildTask
from backend.Agent.src.common.DTO.Request import ChildTaskRequest
from backend.Agent.src.common.IDGeneration.generation_id import IDGenerator
from backend.Agent.src.common.status import Status
from backend.Agent.src.db.task_store import TaskStore
from backend.Agent.src.queue.redis_queue import RedisQueue, AsyncRedisClient
from backend.Agent.src.service.reporterService import ReportAgentService


class ReportTaskManager:
    """Reporter 子任务管理器：消费 research_json，生成最终报告并结束父任务。"""

    def __init__(self, conn, redis_client: AsyncRedisClient):
        # Reporter 是链路最后一环，成功后会把父任务状态更新为 SUCCESS/DONE。
        self.conn = conn
        self.redis_client = redis_client
        self.store = TaskStore(conn)
        self._tasks = {}
        self._service = ReportAgentService()

    _tasks: dict[str, ReportChildTask] = PrivateAttr(default_factory=dict)
    _service: ReportAgentService = PrivateAttr(default_factory=ReportAgentService)

    async def resume_unfinished_tasks(self) -> None:
        # 启动恢复第一步：恢复已有的 PENDING/RUNNING Reporter 子任务。
        recovered_ids: set[str] = set()
        for child_task in self.store.list_recoverable_child_tasks(Status.REPORTER.value):
            if not isinstance(child_task, ReportChildTask):
                continue
            recovered_ids.add(child_task.task_id)
            await self._resume_existing_task(child_task)

        # 启动恢复第二步：父任务停在 REPORTER 但缺少 Reporter 子任务时，按父任务补建。
        for parent_task in self.store.list_recoverable_parents(Status.REPORTER.value):
            if parent_task.plan_json is None or parent_task.research_json is None:
                continue

            latest_child = self.store.get_latest_child_task(parent_task.task_id, Status.REPORTER.value)
            if latest_child is None:
                await self.handle_research_task(self._build_report_payload(parent_task))
                continue
            if latest_child.task_id in recovered_ids:
                continue
            if isinstance(latest_child, ReportChildTask) and latest_child.status == Status.DONE.value:
                await self._finish_successful_task(latest_child)

    async def handle_research_task(self, data: dict):
        # Redis 可能重复投递 Researcher 消息；创建 Reporter 前先做幂等检查。
        existing_task = self.store.get_latest_child_task(data["parent_task_id"], Status.REPORTER.value)
        if isinstance(existing_task, ReportChildTask):
            if existing_task.status in {Status.PENDING.value, Status.RUNNING.value} and existing_task.result is None:
                await self._resume_existing_task(existing_task)
                return
            if existing_task.status == Status.DONE.value:
                await self._finish_successful_task(existing_task)
                return
            if existing_task.status == Status.FAILED.value:
                # FAILED 不自动恢复，避免重启后无限失败重试。
                # TODO: 后续做手动 retry 时再允许显式重跑 FAILED reporter 任务。
                print(f"reporter task already failed, skip parent={data['parent_task_id']}")
                return

        id_generator = IDGenerator()
        task_id = id_generator.generate_id()

        # Reporter 直接使用队列中的 plan_json/research_json，不再通过 IDs 回查聚合。
        input_data = {
            "topic": data.get("topic"),
            "language": data.get("language"),
            "report_format": data.get("report_format"),
            "plan_json": data["plan_json"],
            "research_json": data["research_json"],
        }

        task = ReportChildTask(
            task_id=task_id,
            parent_task_id=data["parent_task_id"],
            status=Status.PENDING.value,
            stage=Status.REPORTER.value,
            input_data=input_data,
        )

        self._tasks[task_id] = task
        self.store.insert_child_task(task)
        self.store.update_parent_child_id(task.parent_task_id, Status.REPORTER.value, task.task_id)
        self.store.update_parent_stage(task.parent_task_id, Status.REPORTER.value, Status.RUNNING.value)

        await self._resume_existing_task(task)

    async def get_task(self, task_id: str) -> Optional[ReportChildTask]:
        # 查询优先返回内存缓存；重启后从数据库查询。
        task = self._tasks.get(task_id)
        if task is not None:
            return task
        child_task = self.store.get_child_task(task_id)
        if isinstance(child_task, ReportChildTask):
            return child_task
        return None

    async def _resume_existing_task(self, task: ReportChildTask) -> None:
        # 恢复和新建共用执行路径，确保状态更新一致。
        self._tasks[task.task_id] = task
        await self._execute_task(task.task_id)

        task = self._tasks[task.task_id]
        if task.status == Status.DONE.value:
            await self._finish_successful_task(task)

    async def _finish_successful_task(self, task: ReportChildTask) -> None:
        # 只有父任务仍停在 REPORTER 时才标记最终成功，避免重复消息重复收尾。
        parent_task = self.store.get_parent_task(task.parent_task_id)
        if parent_task is not None and parent_task.current_stage != Status.REPORTER.value:
            return

        self.store.update_parent_result(
            task.parent_task_id,
            report_text=task.result["report_text"],
            current_stage=Status.DONE.value,
            status=Status.SUCCESS.value,
        )

    async def _execute_task(self, task_id: str) -> None:
        # Agent 执行前把 Reporter 子任务持久化为 RUNNING。
        task = self._tasks[task_id]
        task.status = Status.RUNNING.value
        self._tasks[task_id] = task
        self.store.update_child_status(task_id, Status.RUNNING.value)

        try:
            request = ChildTaskRequest(
                parent_task_id=task.parent_task_id,
                child_task_id=task.task_id,
                input_data=task.input_data,
            )
            report_text = await self._service.generate_report(request)

            task.status = Status.DONE.value
            task.result = {"report_text": report_text}
            self._tasks[task_id] = task
            self.store.update_child_result(task_id, task.result)
        except Exception as exc:
            task.status = Status.FAILED.value
            task.error = (
                f"reporter child task {task_id} failed with {type(exc).__name__}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            self._tasks[task_id] = task
            self.store.update_child_error(task_id, task.error)
            self.store.update_parent_error(task.parent_task_id, task.error)

    def _build_report_payload(self, parent_task: ParentTask) -> dict:
        # 父任务恢复成和 Researcher -> Reporter Redis 消息一致的 payload。
        return {
            "parent_task_id": parent_task.task_id,
            "topic": parent_task.topic,
            "language": parent_task.language,
            "report_format": parent_task.report_format,
            "plan_json": parent_task.plan_json,
            "research_json": parent_task.research_json,
        }

    async def consume_research_queue(self, stop_event: asyncio.Event):
        # Worker 主循环：消费 Researcher -> Reporter 队列。
        while not stop_event.is_set():
            item = await self.redis_client.client.brpop(
                RedisQueue.research_to_reporter_queue,
                timeout=1,
            )

            if item is None:
                continue

            _, raw_data = item
            task_data = json.loads(raw_data)

            try:
                await self.handle_research_task(task_data)
            except Exception as exc:
                print(f"reporter consume failed: {exc}")
