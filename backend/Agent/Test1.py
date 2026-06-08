import psycopg2 as pg

# # 连接 PostgreSQL
# conn = pg.connect(
#     host='127.0.0.1', port=5432, dbname='Test',
#     password='0987321M.n'
# )
# cursor = conn.cursor()
#
# # 执行 SQL 查询语句
# cursor.execute("SELECT * FROM user_infos")
#
# # 获取 SQL 查询结果
# records = cursor.fetchall()
# print(records)
#
# # 关闭连接
# cursor.close()
# conn.close()
#
# # TODO
# #    1.数据恢复
# #    2.日志系统
#
#
# from fastapi import FastAPI, BackgroundTasks
# import asyncio
#
# app = FastAPI()
#
# # 创建一个异步队列
# task_queue = asyncio.Queue(maxsize=100)
#
# async def worker():
#     """后台消费者：持续从队列中取出任务并处理"""
#     while True:
#         task_data = await task_queue.get()   # 异步阻塞，不会阻塞事件循环
#         print(f"处理任务: {task_data}")
#         # 模拟耗时操作（必须用异步方式，例如 asyncio.sleep）
#         await asyncio.sleep(1)
#         # 标记任务完成（如果需要 join 功能）
#         task_queue.task_done()
#
# @app.on_event("startup")
# async def startup_event():
#     # 应用启动时启动一个后台消费者任务
#     asyncio.create_task(worker())
#
# @app.post("/enqueue")
# async def enqueue_task(data: str):
#     """端点：向队列中添加任务"""
#     await task_queue.put(data)
#     return {"message": "任务已入队"}
#
# @app.get("/queue-size")
# async def get_queue_size():
#     return {"size": task_queue.qsize()}

# app/core/redis_client_async.py
import redis.asyncio as redis
from .config import settings

class AsyncRedisClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.pool = None
        return cls._instance

    async def connect(self):
        self.pool = redis.ConnectionPool.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=settings.REDIS_DECODE_RESPONSES,
            password=settings.REDIS_PASSWORD,
        )
        self.client = redis.Redis(connection_pool=self.pool)

    async def close(self):
        await self.client.close()

    async def ping(self):
        return await self.client.ping()

async_redis = AsyncRedisClient()

# lifespan 中调用 async_redis.connect() 和 async_redis.close()

