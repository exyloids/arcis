from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ARCIS_",
        extra="ignore",
    )

    env: str = "development"
    log_level: str = "INFO"
    version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://arcis:arcis@localhost:5432/arcis"
    redis_url: str = "redis://localhost:6379/0"
    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_bucket: str = "arcis-local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
