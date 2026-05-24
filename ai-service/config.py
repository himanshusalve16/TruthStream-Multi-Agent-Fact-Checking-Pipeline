from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "truthstream"
    db_user: str = "postgres"
    db_password: str = "postgres"

    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"
    gemini_api_key_1: str = "replace-me"
    gemini_api_key_2: str | None = None
    gemini_api_key_3: str | None = None
    gemini_api_key_4: str | None = None
    gemini_model: str = "gemini-2.5-flash-lite"
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