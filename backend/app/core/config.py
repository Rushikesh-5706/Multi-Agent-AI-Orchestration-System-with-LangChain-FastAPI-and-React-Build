from __future__ import annotations

import functools

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: str
    REDIS_URL: str
    LLM_API_KEY: str
    LLM_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_RETRIES: int = 3

    OPENWEATHER_API_KEY: str = ""

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    MAX_PLAN_STEPS: int = 5
    MAX_TOOL_ITERATIONS: int = 4
    MAX_TOOL_OUTPUT_CHARS: int = 1500
    TOOL_TIMEOUT_SECONDS: int = 45
    WORKFLOW_TIMEOUT_SECONDS: int = 300
    TOOL_SIMULATED_DELAY_SECONDS: int = 0
    WS_HEARTBEAT_SECONDS: int = 15

    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
