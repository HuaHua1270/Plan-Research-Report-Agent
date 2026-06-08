import asyncio
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from backend.Agent.src.Manager.PlannerManager import PlannerTaskManager
from backend.Agent.src.db.config import database_path
from backend.Agent.src.queue.redis_queue import async_redis


conn = sqlite3.connect(
    database_path,
    timeout=10,  # 数据库锁定等待时间（秒）
    isolation_level='IMMEDIATE',  # 事务隔离级别
    detect_types=sqlite3.PARSE_DECLTYPES  # 启用类型转换
)



planner_task_manager = PlannerTaskManager(conn = conn , redis_client = async_redis)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：建立异步 Redis 连接
    await async_redis.connect()
    print("✅ Async Redis connected")

    # 启动 Redis consumer 前，先从 SQLite 恢复未完成的 Planner 子任务。
    # 这样服务重启后不会只等待新消息，而是会继续执行数据库中断点前的任务。
    await planner_task_manager.resume_unfinished_tasks()

    # 异步停止事件（控制生命周期）
    stop_event = asyncio.Event()
    # 消费任务
    consumer_task = asyncio.create_task(
        planner_task_manager.consume_parent_queue(stop_event)
    )

    app.state.consumer_task = consumer_task
    app.state.stop_event = stop_event

    yield
    # 设置停止事件
    stop_event.set()
    # 取消消费者任务
    consumer_task.cancel()
    # 等待任务完成
    await asyncio.gather(consumer_task, return_exceptions=True)

    # 关闭时：释放资源
    await async_redis.close()
    conn.close()
    print("🛑 Async Redis closed")

app = FastAPI(title="Planner Agent Service" , lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "planner"}


# @app.post("/planner/tasks")
# async def create_planner_task(request: ChildTaskRequest):
#     task = await planner_task_manager(request)
#     return task.model_dump()


@app.get("/planner/tasks/{task_id}")
async def get_planner_task(task_id: str):
    task = await planner_task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Agent.src.controller.planner_Controller:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
    )
