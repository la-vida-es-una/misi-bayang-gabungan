"""
Settings module for MISI BAYANG.

Loads configuration from .env file using pydantic-settings.
Provides singleton access via get_settings() and centralized LLM instantiation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── LLM provider ────────────────────────────────────────────────
    MODEL_NAME: str = "meta-llama/llama-3.1-8b-instruct"
    MODEL_KEY: str = "changeme"
    MODEL_BASE_URL: str = "https://openrouter.ai/api/v1"
    USE_LOCAL_LLM: bool = False

    # ── Mission parameters ──────────────────────────────────────────
    GRID_SIZE: int = 20
    BATTERY_RECALL_THRESHOLD: int = 25
    MAX_MISSION_STEPS: int = 50

    # ── Logging ─────────────────────────────────────────────────────
    LOG_DIR: str = "logs"
    LOG_LEVEL: str = "INFO"
    TRACE_FUNCTION_CALLS: bool = False

    # ── Generation parameters ───────────────────────────────────────
    TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 1024
    NUM_CTX: int = 8192

    def get_llm(self):
        """
        Return a LangChain chat model instance.

        * USE_LOCAL_LLM=False → ChatOpenAI pointed at MODEL_BASE_URL (OpenRouter)
        * USE_LOCAL_LLM=True  → ChatOpenAI pointed at MODEL_BASE_URL (ramalama/OpenAI-compat)

        ramalama serves an OpenAI-compatible REST API (/v1/chat/completions),
        NOT the Ollama wire protocol — so both paths use ChatOpenAI.

        This is the **ONLY** place LLM is instantiated in the entire codebase.
        """
        from langchain_openai import ChatOpenAI

        api_key = "local" if self.USE_LOCAL_LLM else self.MODEL_KEY
        extra: dict = {}
        if self.USE_LOCAL_LLM:
            extra["extra_body"] = {"num_ctx": self.NUM_CTX}

        return ChatOpenAI(
            model=self.MODEL_NAME,
            api_key=api_key,
            base_url=self.MODEL_BASE_URL,
            temperature=self.TEMPERATURE,
            max_tokens=self.MAX_TOKENS,  # pyright: ignore[reportCallIssue]
            **extra,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton factory for application settings."""
    return Settings()
