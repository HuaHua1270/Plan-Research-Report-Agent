import json

from backend.Agent.src.common.DO.Task import ParentTask
from backend.Agent.src.common.DTO.Request import ResearchTaskRequest
from backend.Agent.src.common.DTO.Respones import ResearchTaskResponse
from backend.Agent.src.common.IDGeneration.generation_id import IDGenerator
from backend.Agent.src.common.status import Status
from backend.Agent.src.db.task_store import TaskStore
from backend.Agent.src.queue.redis_queue import AsyncRedisClient, RedisQueue


class ParentManager:
    """父任务管理器：负责接收用户请求、创建父任务并投递 Planner 队列。"""

    def __init__(self, conn, redis_client: AsyncRedisClient):
        # 当前进程内共享同一个 SQLite 连接和 Redis 客户端。
        # TODO: 后续如果接入连接池，需要把 TaskStore 的生命周期放到统一 ServiceManager 中。
        self.conn = conn
        self.redis_client = redis_client
        self.store = TaskStore(conn)

    async def create_task(self, req: ResearchTaskRequest):
        # 1. 接收 controller 传入的用户请求，并生成全局父任务 ID。
        id_generator = IDGenerator()

        # 2. 父任务一创建就进入 RUNNING/PLANNER，表示主流程已经开始等待 Planner 处理。
        # TODO: 如果未来支持“提交但暂不执行”，这里可以先写 PENDING，再由调度器改为 RUNNING。
        parent_task = ParentTask(
            task_id=id_generator.generate_id(),
            status=Status.RUNNING.value,
            current_stage=Status.PLANNER.value,
            topic=req.topic,
            language=req.language,
            depth=req.depth,
            max_subtopics=req.max_subtopics,
            need_citations=req.need_citations,
            report_format=req.report_format,
            user_id=req.user_id,
        )

        # 3. 先落库，再投递队列；这样即使 Redis 投递失败，也能从数据库看到任务。
        self.store.insert_parent_task(parent_task)

        # 4. 构造 Planner 所需的轻量消息，不把数据库整行对象直接塞进 Redis。
        queue_data = self.creat_queue_data(parent_task)
        await self.redis_client.client.lpush(
            RedisQueue.parent_to_planner_queue,
            json.dumps(queue_data, ensure_ascii=False),
        )

        return ResearchTaskResponse(
            task_id=parent_task.task_id,
            status=parent_task.status,
            current_stage=parent_task.current_stage,
            topic=parent_task.topic,
            language=parent_task.language,
            depth=parent_task.depth,
            max_subtopics=parent_task.max_subtopics,
            need_citations=parent_task.need_citations,
            report_format=parent_task.report_format,
            user_id=parent_task.user_id,
        )

    def creat_queue_data(self, parent_task) -> dict:
        # Planner 阶段需要这些上下文来生成 plan_json，并继续传给后续阶段。
        # TODO: 方法名保留为 creat_queue_data 以避免破坏现有调用，后续可统一重命名为 create_queue_data。
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

    async def get_task(self, task_id: str) -> ResearchTaskResponse | None:
        # 查询以数据库为准，避免服务重启后内存 _tasks 丢失导致查不到任务。
        task = self.store.get_parent_task(task_id)
        if task is None:
            return None

        # 将数据库中的 ParentTask 转为 controller 对外返回的 DTO。
        return ResearchTaskResponse(
            task_id=task.task_id,
            status=task.status,
            current_stage=task.current_stage,
            topic=task.topic,
            language=task.language,
            depth=task.depth,
            max_subtopics=task.max_subtopics,
            need_citations=task.need_citations,
            report_format=task.report_format,
            user_id=task.user_id,
            planner_task_id=task.planner_task_id,
            research_task_id=task.research_task_id,
            reporter_task_id=task.reporter_task_id,
            plan_json=task.plan_json,
            research_json=task.research_json,
            report_text=task.report_text,
            error=task.error,
        )
