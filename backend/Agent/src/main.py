from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request

from backend.Agent.src.Manager.ParentManager import ParentManager
from backend.Agent.src.Manager.PlannerManager import PlannerTaskManager
from backend.Agent.src.Manager.ReporterManager import ReportTaskManager
from backend.Agent.src.Manager.SummarizerManager import ResearchTaskManager
from backend.Agent.src.common.DTO.Request import ResearchTaskRequest
from backend.Agent.src.db.config import database_path, settings
from backend.Agent.src.queue.redis_queue import async_redis


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent.main")


ConsumerFactory = Callable[[asyncio.Event], Awaitable[None]]


@dataclass
class AppServices:
    """当前进程内共享的服务对象。

    main.py 采用单进程启动方式后，API 路由和三个后台 consumer 会共享同一组
    SQLite/Redis/Manager 实例。统一挂到 app.state.services，避免每个路由或
    consumer 自己重复初始化资源。
    """

    conn: sqlite3.Connection
    parent_manager: ParentManager
    planner_manager: PlannerTaskManager
    research_manager: ResearchTaskManager
    report_manager: ReportTaskManager
    stop_event: asyncio.Event
    consumer_tasks: dict[str, asyncio.Task]


def create_sqlite_connection() -> sqlite3.Connection:
    """创建 SQLite 连接，并设置本进程需要的基础 pragma。

    SQLite 的外键约束默认不会自动启用，需要每个连接显式设置。
    busy_timeout 用来降低多个后台任务短时间连续写库时的锁冲突概率。
    WAL 可以提升读写并发稳定性；如果当前环境不支持 WAL，启动不应因此失败。
    """

    conn = sqlite3.connect(
        database_path,
        timeout=settings.SQLITE_TIMEOUT,
        check_same_thread=False,
    )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(settings.SQLITE_TIMEOUT * 1000)}")

    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError as exc:
        # WAL 是优化项，不是启动硬依赖；某些只读或特殊文件系统下可能无法开启。
        logger.warning("enable sqlite WAL failed, continue without WAL: %s", exc)

    return conn


async def resume_unfinished_tasks(services: AppServices) -> None:
    """启动恢复入口。

    恢复顺序按业务链路从上到下执行：
    1. Planner 处理停留在 PLANNER 的父任务或未完成 Planner 子任务。
    2. Researcher 处理停留在 RESEARCH 的父任务以及未完成研究子任务。
    3. Reporter 处理停留在 REPORTER 的父任务或未完成 Reporter 子任务。

    这样即使上次服务在 Agent 执行完成前退出，也能根据数据库状态继续推进。
    """

    logger.info("resume planner tasks")
    await services.planner_manager.resume_unfinished_tasks()

    logger.info("resume research tasks")
    await services.research_manager.resume_unfinished_tasks()

    logger.info("resume reporter tasks")
    await services.report_manager.resume_unfinished_tasks()


def start_consumer_tasks(services: AppServices) -> None:
    """启动三个后台队列消费循环。

    每个 consumer 都拿同一个 stop_event。关闭时先 set stop_event，consumer 的
    Redis brpop/brpop timeout 到期后会自然退出，避免 Ctrl+C 时卡在阻塞读取。
    """

    consumers: dict[str, ConsumerFactory] = {
        "planner": services.planner_manager.consume_parent_queue,
        "research": services.research_manager.consume_plan_queue,
        "reporter": services.report_manager.consume_research_queue,
    }

    for name, consumer in consumers.items():
        task = asyncio.create_task(consumer(services.stop_event), name=f"{name}-consumer")
        services.consumer_tasks[name] = task
        logger.info("started %s consumer", name)


async def stop_consumer_tasks(services: AppServices, timeout: float = 10.0) -> None:
    """优雅停止后台 consumer。

    先通知 consumer 不再拉新消息，再等待当前任务自然结束；如果超时仍未结束，
    说明可能卡在 Agent 或外部调用中，此时再 cancel，保证进程可以退出。
    """

    services.stop_event.set()
    tasks = list(services.consumer_tasks.values())
    if not tasks:
        return

    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in done:
        if task.cancelled():
            continue
        exc = task.exception()
        if exc is not None:
            logger.warning("consumer task exited with error: %s", exc)

    for task in pending:
        logger.warning("consumer task timeout, cancel: %s", task.get_name())
        task.cancel()

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def build_services(conn: sqlite3.Connection) -> AppServices:
    """组装 API 和后台任务共用的 Manager。

    ParentManager 负责接收 API 请求并写入 parent_tasks；
    Planner/Research/Reporter 三个 Manager 负责各自阶段的恢复、执行和入队。
    """

    return AppServices(
        conn=conn,
        parent_manager=ParentManager(conn, async_redis),
        planner_manager=PlannerTaskManager(conn, async_redis),
        research_manager=ResearchTaskManager(conn, async_redis),
        report_manager=ReportTaskManager(conn, async_redis),
        stop_event=asyncio.Event(),
        consumer_tasks={},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期。

    startup 阶段完成所有资源初始化和任务恢复；shutdown 阶段统一释放后台
    consumer、Redis 和 SQLite，确保 main.py 是整个项目唯一启动入口。
    """

    conn: sqlite3.Connection | None = None
    services: AppServices | None = None

    try:
        conn = create_sqlite_connection()
        await async_redis.connect()

        # Manager 构造时会创建 TaskStore，并通过 TaskStore.ensure_schema() 建表。
        services = build_services(conn)
        app.state.services = services

        await resume_unfinished_tasks(services)
        start_consumer_tasks(services)

        logger.info("agent main app started")
        yield
    finally:
        if services is not None:
            await stop_consumer_tasks(services)

        try:
            await async_redis.close()
        except Exception as exc:
            logger.warning("close redis failed: %s", exc)

        if conn is not None:
            conn.close()
            logger.info("sqlite connection closed")


app = FastAPI(
    title="Plan Research Report Agent",
    lifespan=lifespan,
)


def get_services(request: Request) -> AppServices:
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="services are not initialized")
    return services


@app.get("/health")
async def health(request: Request):
    """健康检查。

    返回 DB、Redis 和三个后台 consumer 的基本状态，方便开发时判断 main.py
    是否已经完整接管 API 与队列消费。
    """

    services = get_services(request)

    db_ok = True
    try:
        services.conn.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        await async_redis.ping()
    except Exception:
        redis_ok = False

    consumer_status = {
        name: {
            "done": task.done(),
            "cancelled": task.cancelled(),
        }
        for name, task in services.consumer_tasks.items()
    }

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "consumers": consumer_status,
    }


@app.post("/research-tasks")
async def create_research_task(request: Request, payload: ResearchTaskRequest):
    """创建父任务。

    ParentManager 会负责写入 parent_tasks，并把轻量消息投递到 Planner 队列。
    """

    services = get_services(request)
    return await services.parent_manager.create_task(payload)


@app.get("/research-tasks/{task_id}")
async def get_research_task(request: Request, task_id: str):
    services = get_services(request)
    task = await services.parent_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="parent task not found")
    return task


@app.get("/planner/tasks/{task_id}")
async def get_planner_task(request: Request, task_id: str):
    services = get_services(request)
    task = await services.planner_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="planner task not found")
    return task


@app.get("/research/tasks/{task_id}")
async def get_research_child_task(request: Request, task_id: str):
    services = get_services(request)
    task = await services.research_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="research task not found")
    return task


@app.get("/research/tasks/by-parent/{parent_task_id}")
async def list_research_tasks_by_parent(request: Request, parent_task_id: str):
    services = get_services(request)
    return await services.research_manager.list_tasks_by_parent(parent_task_id)


@app.get("/report/tasks/{task_id}")
async def get_report_task(request: Request, task_id: str):
    services = get_services(request)
    task = await services.report_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="report task not found")
    return task


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Agent.src.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
