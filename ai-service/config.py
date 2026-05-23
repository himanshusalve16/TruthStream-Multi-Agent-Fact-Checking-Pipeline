from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/truthstream"
    redis_url: str = "redis://localhost:6379"
    openai_api_key: str = "sk-replace-me"
    serpapi_key: str = "replace-me"  # optional; DuckDuckGo used if unset or empty
    internal_api_secret: str = "replace-me"
    test_mode: bool = False

    class Config:
        # In Docker, env vars come from the compose environment block.
        # When running locally outside Docker, optionally load from a .env file.
        # Use an absolute-style relative path that works from the repo root.
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()