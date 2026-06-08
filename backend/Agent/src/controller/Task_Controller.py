import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from backend.Agent.src.common.DTO.Request import  ResearchTaskRequest
from backend.Agent.src.Manager.ParentManager import ParentManager

from backend.Agent.src.db.config import database_path

from backend.Agent.src.queue.redis_queue import async_redis

conn = sqlite3.connect(
    database_path,
    timeout=10,  # 数据库锁定等待时间（秒）
    isolation_level='IMMEDIATE',  # 事务隔离级别
    detect_types=sqlite3.PARSE_DECLTYPES  # 启用类型转换
)

@asynccontextmanager
async def lifespan(app: FastAPI):

    # 启动时：建立异步 Redis 连接
    await async_redis.connect()
    print("✅ Async Redis connected")
    yield

    # 关闭时：释放资源
    await async_redis.close()
    conn.close()
    print("🛑 Async Redis closed")
app = FastAPI(title="Father Task Service" , lifespan=lifespan)

parent_manager = ParentManager(conn = conn , redis_client = async_redis)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "task"}

@app.post("/research-tasks")
async def create_parent_task(request: ResearchTaskRequest):
    task = await parent_manager.create_task(request)
    return task.model_dump()


@app.get("/report/tasks/{task_id}")
async def get_parent_task(task_id: str):
    task = await parent_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Agent.src.controller.Task_Controller:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
