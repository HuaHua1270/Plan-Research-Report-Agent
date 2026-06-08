from __future__ import annotations

import asyncio
import json
import traceback
from typing import Any, Optional

from pydantic import PrivateAttr

from backend.Agent.src.common.DO.Task import ParentTask, ResearchChildTask
from backend.Agent.src.common.DTO.Request import ChildTaskRequest
from backend.Agent.src.common.IDGeneration.generation_id import IDGenerator
from backend.Agent.src.common.status import Status
from backend.Agent.src.db.task_store import TaskStore
from backend.Agent.src.queue.redis_queue import AsyncRedisClient, RedisQueue
from backend.Agent.src.service.summarizerService import SummarizerAgentService


class ResearchTaskManager:
    """Research 子任务管理器：拆分 plan_json.subtopics，逐个执行研究任务并聚合结果。"""

    def __init__(self, conn, redis_client: AsyncRedisClient):
        # 同一个父任务会对应多条 RESEARCH 子任务，状态和结果都以 child_tasks 表为准。
        self.conn = conn
        self.redis_client = redis_client
        self.store = TaskStore(conn)
        self._tasks = {}
        self._service = SummarizerAgentService()

    _tasks: dict[str, ResearchChildTask] = PrivateAttr(default_factory=dict)
    _service: SummarizerAgentService = PrivateAttr(default_factory=SummarizerAgentService)

    async def resume_unfinished_tasks(self) -> None:
        # 启动恢复第一步：找到已有的未完成 Research 子任务，按 parent 分组恢复。
        parent_ids: set[str] = set()
        for child_task in self.store.list_recoverable_child_tasks(Status.RESEARCH.value):
            if not isinstance(child_task, ResearchChildTask):
                continue
            parent_task = self.store.get_parent_task(child_task.parent_task_id)
            if parent_task is None or parent_task.current_stage != Status.RESEARCH.value:
                continue
            parent_ids.add(child_task.parent_task_id)

        # 启动恢复第二步：父任务停在 RESEARCH 但还没有 Research 子任务时，按 plan_json 补建。
        for parent_task in self.store.list_recoverable_parents(Status.RESEARCH.value):
            if parent_task.plan_json is None:
                continue
            tasks = self._list_research_tasks(parent_task.task_id)
            if not tasks:
                self._create_research_tasks(self._build_research_payload(parent_task))
            parent_ids.add(parent_task.task_id)

        # 启动恢复第三步：顺序执行每个父任务下未完成的 Research 子任务，再尝试聚合。
        for parent_id in parent_ids:
            await self._run_incomplete_tasks(parent_id)
            await self._finish_parent_if_ready(parent_id)

    async def get_task(self, task_id: str) -> Optional[ResearchChildTask]:
        # 查询优先返回当前进程缓存；缓存不存在时从数据库查询。
        task = self._tasks.get(task_id)
        if task is not None:
            return task
        child_task = self.store.get_child_task(task_id)
        if isinstance(child_task, ResearchChildTask):
            return child_task
        return None

    async def list_tasks_by_parent(self, parent_task_id: str) -> list[ResearchChildTask]:
        # 给 controller 展示某个父任务下所有 Research 子任务的状态和结果。
        return self._list_research_tasks(parent_task_id)

    async def handle_plan_task(self, request: dict):
        parent_id = request["parent_task_id"]
        parent_task = self.store.get_parent_task(parent_id)
        if parent_task is not None and parent_task.current_stage != Status.RESEARCH.value:
            # 父任务已经被推进到后续阶段时，重复 Planner 消息不再创建/执行 Research 子任务。
            return

        existing_tasks = self._list_research_tasks(parent_id)
        if not existing_tasks:
            # 第一次收到 Planner 消息时，根据 subtopics 创建多条 RESEARCH 子任务。
            existing_tasks = self._create_research_tasks(request)

        if any(task.status == Status.FAILED.value for task in existing_tasks):
            # FAILED 不自动恢复，避免重复消息或重启后无限重试。
            # TODO: 后续提供手动 retry 接口时，再允许重跑失败的 subtopic。
            self.store.update_parent_error(parent_id, f"research parent {parent_id} has failed child task")
            return

        await self._run_incomplete_tasks(parent_id)
        await self._finish_parent_if_ready(parent_id)

    def _create_research_tasks(self, request: dict) -> list[ResearchChildTask]:
        # 把 plan_json.subtopics 拆成多条可查询、可恢复的 Research 子任务。
        id_generator = IDGenerator()
        parent_id = request["parent_task_id"]
        plan_json = request["plan_json"]
        subtopics = self._extract_subtopics(plan_json)
        total = len(subtopics)
        tasks: list[ResearchChildTask] = []

        for index, subtopic in enumerate(subtopics, start=1):
            task = ResearchChildTask(
                task_id=id_generator.generate_id(),
                parent_task_id=parent_id,
                status=Status.PENDING.value,
                stage=Status.RESEARCH.value,
                input_data={
                    "topic": request.get("topic"),
                    "language": request.get("language"),
                    "depth": request.get("depth"),
                    "need_citations": request.get("need_citations"),
                    "report_format": request.get("report_format"),
                    "plan_json": plan_json,
                    "subtopic": subtopic,
                    "subtopic_index": index,
                    "subtopic_total": total,
                },
            )
            self._tasks[task.task_id] = task
            self.store.insert_child_task(task)
            tasks.append(task)

        # parent_tasks.research_task_id 只保留第一条 Research 子任务 ID 作为兼容字段。
        self.store.update_parent_child_id(parent_id, Status.RESEARCH.value, tasks[0].task_id)
        self.store.update_parent_stage(parent_id, Status.RESEARCH.value, Status.RUNNING.value)
        return tasks

    async def _run_incomplete_tasks(self, parent_id: str) -> None:
        # 逐条执行未完成的子任务；当前 Agent 使用全局实例，先保持顺序执行最稳。
        for task in self._list_research_tasks(parent_id):
            if task.status == Status.FAILED.value:
                self.store.update_parent_error(parent_id, task.error or "research child task failed")
                return
            if task.status in {Status.PENDING.value, Status.RUNNING.value} and task.result is None:
                self._tasks[task.task_id] = task
                await self._execute_task(task.task_id)
                task = self._tasks[task.task_id]
                if task.status == Status.FAILED.value:
                    return

    async def _finish_parent_if_ready(self, parent_id: str) -> None:
        # 只有全部 Research 子任务完成后，才聚合 research_json 并推给 Reporter。
        parent_task = self.store.get_parent_task(parent_id)
        if parent_task is None or parent_task.current_stage != Status.RESEARCH.value:
            return

        tasks = self._list_research_tasks(parent_id)
        if not tasks:
            return

        failed_task = next((task for task in tasks if task.status == Status.FAILED.value), None)
        if failed_task is not None:
            self.store.update_parent_error(parent_id, failed_task.error or "research child task failed")
            return

        if any(task.status != Status.DONE.value or task.result is None for task in tasks):
            return

        research_json = self._aggregate_research_json(tasks)
        first_task = tasks[0]
        self.store.update_parent_result(
            parent_id,
            research_json=research_json,
            current_stage=Status.REPORTER.value,
            status=Status.RUNNING.value,
        )
        await self._send_message(
            parent_id=parent_id,
            topic=first_task.input_data.get("topic"),
            language=first_task.input_data.get("language"),
            report_format=first_task.input_data.get("report_format"),
            plan_json=first_task.input_data["plan_json"],
            research_json=research_json,
        )

    async def _send_message(
        self,
        parent_id: str,
        topic: str | None,
        language: str | None,
        report_format: str | None,
        plan_json: dict,
        research_json: dict,
    ):
        # Reporter 继续接收聚合后的完整 research_json，因此下游接口保持不变。
        queue_data = {
            "parent_task_id": parent_id,
            "topic": topic,
            "language": language,
            "report_format": report_format,
            "plan_json": plan_json,
            "research_json": research_json,
        }
        await self.redis_client.client.lpush(
            RedisQueue.research_to_reporter_queue,
            json.dumps(queue_data, ensure_ascii=False),
        )

    async def _execute_task(self, task_id: str) -> None:
        # Agent 执行前把单个 subtopic 子任务持久化为 RUNNING。
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
            research_json = await self._service.generate_research(request)

            task.status = Status.DONE.value
            task.result = {"research_json": research_json}
            self._tasks[task_id] = task
            self.store.update_child_result(task_id, task.result)
        except Exception as exc:
            task.status = Status.FAILED.value
            task.error = (
                f"research child task {task_id} failed with {type(exc).__name__}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            self._tasks[task_id] = task
            self.store.update_child_error(task_id, task.error)
            self.store.update_parent_error(task.parent_task_id, task.error)

    def _list_research_tasks(self, parent_id: str) -> list[ResearchChildTask]:
        tasks = self.store.list_child_tasks(parent_id, Status.RESEARCH.value)
        research_tasks = [task for task in tasks if isinstance(task, ResearchChildTask)]
        return sorted(research_tasks, key=self._task_order)

    def _task_order(self, task: ResearchChildTask) -> int:
        return int(task.input_data.get("subtopic_index") or 0)

    def _extract_subtopics(self, plan_json: Any) -> list[dict[str, Any]]:
        # 与 SummarizerAgentService 的解析规则保持一致，让 Manager 负责拆分任务。
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

    def _aggregate_research_json(self, tasks: list[ResearchChildTask]) -> dict[str, Any]:
        # 把多条 subtopic 结果聚合回 Reporter 已支持的 task_summaries 格式。
        task_summaries: list[dict[str, Any]] = []
        plan_json = tasks[0].input_data.get("plan_json")

        for task in sorted(tasks, key=self._task_order):
            result = task.result or {}
            item = result.get("research_json", result)
            if isinstance(item, dict) and isinstance(item.get("task_summaries"), list):
                task_summaries.extend(item["task_summaries"])
                continue
            if not isinstance(item, dict):
                item = {"summary": str(item)}
            task_summaries.append(
                {
                    "index": int(item.get("index") or task.input_data.get("subtopic_index") or 0),
                    "title": item.get("title") or task.input_data.get("subtopic", {}).get("title", ""),
                    "intent": item.get("intent") or task.input_data.get("subtopic", {}).get("intent", ""),
                    "query": item.get("query") or task.input_data.get("subtopic", {}).get("query", ""),
                    "summary": item.get("summary", ""),
                }
            )

        task_summaries.sort(key=lambda item: int(item.get("index") or 0))
        return {
            "task_summaries": task_summaries,
            "summary": self._join_summaries(task_summaries),
            "plan_json": plan_json,
        }

    def _join_summaries(self, task_summaries: list[dict[str, Any]]) -> str:
        sections = []
        for item in task_summaries:
            sections.append(
                f"## {item.get('index', '')}. {item.get('title', '')}\n\n"
                f"Intent: {item.get('intent', '')}\n\n"
                f"Query: {item.get('query', '')}\n\n"
                f"{item.get('summary', '')}"
            )
        return "\n\n".join(sections)

    def _build_research_payload(self, parent_task: ParentTask) -> dict:
        # 父任务恢复成和 Planner -> Researcher Redis 消息一致的 payload。
        return {
            "parent_task_id": parent_task.task_id,
            "topic": parent_task.topic,
            "language": parent_task.language,
            "depth": parent_task.depth,
            "need_citations": parent_task.need_citations,
            "report_format": parent_task.report_format,
            "plan_json": parent_task.plan_json,
        }

    async def consume_plan_queue(self, stop_event: asyncio.Event) -> None:
        # Worker 主循环：消费 Planner -> Researcher 队列。
        while not stop_event.is_set():
            item = await self.redis_client.client.brpop(
                RedisQueue.planner_to_reacher_queue,
                timeout=1,
            )

            if item is None:
                continue

            _, raw_data = item
            task_data = json.loads(raw_data)

            try:
                await self.handle_plan_task(task_data)
            except Exception as exc:
                print(f"research consume failed: {exc}")
