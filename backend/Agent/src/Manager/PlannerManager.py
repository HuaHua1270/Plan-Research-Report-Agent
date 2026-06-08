from __future__ import annotations

import asyncio
import json
import traceback
from typing import Optional

from pydantic import PrivateAttr

from backend.Agent.src.common.DO.Task import ParentTask, PlannerChildTask
from backend.Agent.src.common.DTO.Request import ChildTaskRequest
from backend.Agent.src.common.IDGeneration.generation_id import IDGenerator
from backend.Agent.src.common.status import Status
from backend.Agent.src.db.task_store import TaskStore
from backend.Agent.src.queue.redis_queue import AsyncRedisClient, RedisQueue
from backend.Agent.src.service.plannerSercvice import PlannerAgentService


class PlannerTaskManager:
    """Planner 子任务管理器：消费父任务消息，生成 plan_json，并推进到 Research 阶段。"""

    def __init__(self, conn, redis_client: AsyncRedisClient):
        # Manager 同时维护内存缓存和 SQLite 状态；启动恢复时从数据库重新装回 _tasks。
        self.conn = conn
        self.redis_client = redis_client
        self.store = TaskStore(conn)
        self._tasks = {}
        self._service = PlannerAgentService()

    _tasks: dict[str, PlannerChildTask] = PrivateAttr(default_factory=dict)
    _service: PlannerAgentService = PrivateAttr(default_factory=PlannerAgentService)

    async def resume_unfinished_tasks(self) -> None:
        # 启动恢复第一步：先恢复已有的 PENDING/RUNNING Planner 子任务。
        # TODO: 后续如果 Agent 支持并发安全，可以把这里改成有限并发恢复。
        recovered_ids: set[str] = set()
        for child_task in self.store.list_recoverable_child_tasks(Status.PLANNER.value):
            if not isinstance(child_task, PlannerChildTask):
                continue
            recovered_ids.add(child_task.task_id)
            await self._resume_existing_task(child_task)

        # 启动恢复第二步：父任务停在 PLANNER 但没有可执行子任务时，补建 Planner 子任务。
        for parent_task in self.store.list_recoverable_parents(Status.PLANNER.value):
            latest_child = self.store.get_latest_child_task(parent_task.task_id, Status.PLANNER.value)
            if latest_child is None:
                await self.handle_parent_task(self._build_parent_payload(parent_task))
                continue
            if latest_child.task_id in recovered_ids:
                continue
            if isinstance(latest_child, PlannerChildTask) and latest_child.status == Status.DONE.value:
                await self._finish_successful_task(latest_child)

    async def handle_parent_task(self, request: dict):
        # Redis 可能残留重复消息；创建新子任务前先查同一父任务的最新 Planner 子任务。
        existing_task = self.store.get_latest_child_task(request["task_id"], Status.PLANNER.value)
        if isinstance(existing_task, PlannerChildTask):
            if existing_task.status in {Status.PENDING.value, Status.RUNNING.value} and existing_task.result is None:
                await self._resume_existing_task(existing_task)
                return
            if existing_task.status == Status.DONE.value:
                await self._finish_successful_task(existing_task)
                return
            if existing_task.status == Status.FAILED.value:
                # FAILED 不自动恢复，避免服务重启后反复执行同一个失败任务。
                # TODO: 后续增加手动 retry 接口时，再允许用户显式重试 FAILED 任务。
                print(f"planner task already failed, skip parent={request['task_id']}")
                return

        # 没有可复用子任务时，创建新的 Planner 子任务并写入 PENDING。
        id_generator = IDGenerator()
        task = PlannerChildTask(
            task_id=id_generator.generate_id(),
            parent_task_id=request["task_id"],
            status=Status.PENDING.value,
            stage=Status.PLANNER.value,
            input_data={
                "topic": request["topic"],
                "language": request.get("language"),
                "depth": request.get("depth"),
                "max_subtopics": request.get("max_subtopics"),
                "need_citations": request.get("need_citations"),
                "report_format": request.get("report_format"),
                "user_id": request.get("user_id"),
            },
        )

        self._tasks[task.task_id] = task
        self.store.insert_child_task(task)
        self.store.update_parent_child_id(task.parent_task_id, Status.PLANNER.value, task.task_id)
        self.store.update_parent_stage(task.parent_task_id, Status.PLANNER.value, Status.RUNNING.value)

        await self._resume_existing_task(task)

    async def get_task(self, task_id: str) -> Optional[PlannerChildTask]:
        # 查询优先返回当前进程缓存；服务重启后从数据库查询。
        task = self._tasks.get(task_id)
        if task is not None:
            return task
        child_task = self.store.get_child_task(task_id)
        if isinstance(child_task, PlannerChildTask):
            return child_task
        return None

    async def _resume_existing_task(self, task: PlannerChildTask) -> None:
        # 恢复和新建都走同一条执行路径，确保 RUNNING/DONE/FAILED 写库逻辑一致。
        self._tasks[task.task_id] = task
        await self._execute_task(task.task_id)

        task = self._tasks[task.task_id]
        if task.status == Status.DONE.value:
            await self._finish_successful_task(task)

    async def _finish_successful_task(self, task: PlannerChildTask) -> None:
        # 只有父任务仍停在 PLANNER 时才推进和补发消息，避免重复 Redis 消息造成重复下游任务。
        parent_task = self.store.get_parent_task(task.parent_task_id)
        if parent_task is not None and parent_task.current_stage != Status.PLANNER.value:
            return

        plan_json = task.result["plan_json"]
        self.store.update_parent_result(
            task.parent_task_id,
            plan_json=plan_json,
            current_stage=Status.RESEARCH.value,
            status=Status.RUNNING.value,
        )
        await self._send_message(task.task_id)

    async def _send_message(self, task_id: str):
        # Redis 只承载下一阶段所需上下文，数据库仍然是任务状态的权威来源。
        task = self._tasks[task_id]
        input_data = task.input_data or {}
        queue_data = {
            "parent_task_id": task.parent_task_id,
            "planner_task_id": task.task_id,
            "topic": input_data.get("topic"),
            "language": input_data.get("language"),
            "depth": input_data.get("depth"),
            "need_citations": input_data.get("need_citations"),
            "report_format": input_data.get("report_format"),
            "plan_json": task.result["plan_json"],
        }
        await self.redis_client.client.lpush(
            RedisQueue.planner_to_reacher_queue,
            json.dumps(queue_data, ensure_ascii=False),
        )

    async def _execute_task(self, task_id: str) -> None:
        # Agent 执行前立即标记 RUNNING，方便查询接口展示当前执行状态。
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
            plan_json = await self._service.generate_plan(request)

            task.status = Status.DONE.value
            task.result = {"plan_json": plan_json}
            self._tasks[task_id] = task
            self.store.update_child_result(task_id, task.result)
        except Exception as exc:
            task.status = Status.FAILED.value
            task.error = (
                f"planner child task {task_id} failed with {type(exc).__name__}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            self._tasks[task_id] = task
            self.store.update_child_error(task_id, task.error)
            self.store.update_parent_error(task.parent_task_id, task.error)

    def _build_parent_payload(self, parent_task: ParentTask) -> dict:
        # 父任务恢复成和 Parent -> Planner Redis 消息一致的 payload。
        return {
            "task_id": parent_task.task_id,
            "topic": parent_task.topic,
            "language": parent_task.language,
            "depth": parent_task.depth,
            "max_subtopics": parent_task.max_subtopics,
            "need_citations": parent_task.need_citations,
            "report_format": parent_task.report_format,
            "user_id": parent_task.user_id,
        }

    async def consume_parent_queue(self, stop_event: asyncio.Event) -> None:
        # Worker 主循环：短 timeout 轮询 Redis，便于 stop_event 生效后优雅退出。
        while not stop_event.is_set():
            item = await self.redis_client.client.brpop(
                RedisQueue.parent_to_planner_queue,
                timeout=1,
            )

            if item is None:
                continue

            _, raw_data = item
            task_data = json.loads(raw_data)

            try:
                await self.handle_parent_task(task_data)
            except Exception as exc:
                print(f"planner consume failed: {exc}")
