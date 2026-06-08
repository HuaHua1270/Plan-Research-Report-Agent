# app/core/config.py
from pydantic_settings import BaseSettings

class RedisSettings(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = "123456"
    REDIS_MAX_CONNECTIONS: int = 10
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_DECODE_RESPONSES: bool = True

    class Config:
        env_file = ".env"

settings = RedisSettings()

# {
#   "status": "ok",
#   "db": "ok",
#   "redis": "ok",
#   "consumers": {
#     "planner": {
#       "done": false,
#       "cancelled": false
#     },
#     "research": {
#       "done": false,
#       "cancelled": false
#     },
#     "reporter": {
#       "done": false,
#       "cancelled": false
#     }
#   }
# }