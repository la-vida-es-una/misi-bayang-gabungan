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

    # ── Generation parameters ───────────────────────────────────────
    TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 1024
    NUM_CTX: int = 2048

    def get_llm(self):
        """
        Return a LangChain chat model instance.

        * USE_LOCAL_LLM=False → ChatOpenAI pointed at MODEL_BASE_URL (OpenRouter)
        * USE_LOCAL_LLM=True  → ChatOllama with model=MODEL_NAME (edge / prod)

        This is the **ONLY** place LLM is instantiated in the entire codebase.
        """
        if self.USE_LOCAL_LLM:
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=self.MODEL_NAME,
                base_url=self.MODEL_BASE_URL,
                temperature=self.TEMPERATURE,
                num_ctx=self.NUM_CTX,
            )

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.MODEL_NAME,
            api_key=self.MODEL_KEY,
            base_url=self.MODEL_BASE_URL,
            temperature=self.TEMPERATURE,
            max_tokens=self.MAX_TOKENS,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton factory for application settings."""
    return Settings()
