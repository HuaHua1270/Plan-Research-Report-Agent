from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    This module only reads configuration. It deliberately does not create
    database engines, Redis clients, or other process resources.
    """

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/agent_db",
        alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
