from __future__ import annotations
import redis.asyncio as redis
import logging
from backend.Agent.src.queue.config import settings


logger = logging.getLogger(__name__)

class RedisQueue:
    """Redis队列。"""
    parent_to_planner_queue = "parent_to_planner_queue"
    planner_to_reacher_queue = "planner_to_reacher_queue"
    research_to_reporter_queue = "research_to_reporter_queue"


class AsyncRedisClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.pool = None
        return cls._instance

    async def connect(self):
        # redis连接池
        self.pool = redis.ConnectionPool.from_url(
            # url
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
            # 最大连接数
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            # 解码响应
            decode_responses=settings.REDIS_DECODE_RESPONSES,
            # 密码
            password=settings.REDIS_PASSWORD,
        )
        self.client = redis.Redis(connection_pool=self.pool)
        # 测试连接
        await self.ping()
        logger.info("Async Redis connected")

    async def close(self):
        await self.client.close()
        await self.pool.disconnect()


    async def ping(self):
        return await self.client.ping()


async_redis = AsyncRedisClient()
