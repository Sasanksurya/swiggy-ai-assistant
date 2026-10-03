from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "staging", "production"] = "development"
    # true  -> Mock Swiggy MCP (synthetic data)
    # false -> authorized Swiggy MCP (Stage 2)
    mock_mode: bool = True
    mock_mcp_url: str = "http://localhost:8100"

    database_url: str = "postgresql://swiggy:change-me-locally@localhost:5432/swiggy_assistant"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Assistant
    assistant_name: str = "Sarah"
    session_store: Literal["memory", "redis"] = "memory"
    session_ttl_seconds: int = 3600
    nlu_provider: Literal["rules", "ollama"] = "rules"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    @model_validator(mode="after")
    def _no_mock_in_production(self) -> "Settings":
        if self.app_env == "production" and self.mock_mode:
            raise ValueError("MOCK_MODE must be false when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
