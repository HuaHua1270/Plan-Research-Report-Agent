from pathlib import Path

from pydantic_settings import BaseSettings


AGENT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_DIR = AGENT_DIR / "database"
DEFAULT_DATABASE_PATH = DEFAULT_DATABASE_DIR / "agent.db"
DEFAULT_SCHEMA_FILE = Path(__file__).with_name("init.sql")


class SQLLiteSettings(BaseSettings):
    SQLITE_DB_PATH: str = str(DEFAULT_DATABASE_PATH)
    SQLITE_POOL_SIZE: int = 5
    SQLITE_POOL_MAX_USAGE: int = 100
    SQLITE_TIMEOUT: float = 10.0
    SQLITE_SCHEMA_FILE: str = str(DEFAULT_SCHEMA_FILE)
    SQLITE_SCHEMA_SQL: str = ""

    class Config:
        env_file = ".env"

    def ensure_db_directory(self) -> None:
        db_path = Path(self.SQLITE_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)


settings = SQLLiteSettings()
settings.ensure_db_directory()

database_path = settings.SQLITE_DB_PATH
