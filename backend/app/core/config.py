"""Application configuration using pydantic-settings.

Loads values from environment variables and backend/.env file.
Secrets are never exposed in logs, API responses, or repr output.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("patchpilot.config")

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/app/core -> backend


class Settings(BaseSettings):
    """Central configuration – loaded once at startup."""

    # ── Meta Model API ──────────────────────────────────────────────
    # Official env var per documentation: MODEL_API_KEY
    MODEL_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        repr=False,
        description="Official Bearer token for Meta Model API (starts with LLM_)",
    )
    META_MODEL_ID: str = Field(
        default="muse-spark-1.3",
        description="Model identifier to use for chat completions",
    )
    META_API_BASE_URL: str = Field(
        default="https://api.meta.ai/v1",
        description="Base URL for the Meta Model API",
    )
    META_API_TIMEOUT: int = Field(
        default=120,
        description="HTTP timeout in seconds for Meta API requests",
    )
    META_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum retries for retryable Meta API failures",
    )
    LLM_PROVIDER: str = Field(default="meta")
    GEMINI_API_KEY: SecretStr = Field(default=SecretStr(""), repr=False)
    GEMINI_MODEL_ID: str = Field(default="")
    GEMINI_API_BASE_URL: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    ALLOW_DEV_PROVIDER: bool = Field(default=False)

    @field_validator("LLM_PROVIDER")
    @classmethod
    def _validate_llm_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"meta", "gemini", "demo", "replay"}:
            raise ValueError("LLM_PROVIDER must be one of: meta, gemini, demo, replay")
        return normalized

    @field_validator("GEMINI_API_KEY")
    @classmethod
    def _clean_gemini_key(cls, value: SecretStr) -> SecretStr:
        return SecretStr(value.get_secret_value().strip())

    # ── Application Modes ───────────────────────────────────────────
    APP_ENV: str = Field(default="development")
    DEMO_MODE: bool = Field(
        default=False,
        description="When True, use deterministic simulated responses instead of real Meta API",
    )
    APP_MODE: str = Field(default="public_demo")
    EXECUTION_BACKEND: str = Field(default="none")
    ENABLE_UPLOAD: bool = Field(default=False)
    ALLOWED_ORIGINS: str = Field(default="http://127.0.0.1:3000,http://localhost:3000,https://patchpilot-delta.vercel.app")
    PUBLIC_DAILY_META_CALL_CAP: int = Field(default=200, ge=0)
    PUBLIC_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=3)
    PUBLIC_MAX_TOKENS_PER_CALL: int = Field(default=2048, ge=1, le=2048)
    PUBLIC_AI_ENABLED: bool = Field(default=False)
    PUBLIC_DEMO_ENABLED: bool = Field(default=False)

    # ── Sandbox Isolation Policy ────────────────────────────────────
    # ── Database ────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default=f"sqlite:///{_BACKEND_DIR / 'database' / 'patchpilot.db'}",
        description="SQLAlchemy database URL",
    )

    # ── Execution limits ────────────────────────────────────────────
    MAX_REPAIR_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    max_attempts: int = Field(default=3, ge=1)
    MAX_UPLOAD_SIZE_MB: int = Field(default=50)

    # ── Pydantic-settings ──────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Validators ──────────────────────────────────────────────────
    @field_validator("MODEL_API_KEY")
    @classmethod
    def _clean_key(cls, v: SecretStr) -> SecretStr:
        return SecretStr(v.get_secret_value().strip())

    @field_validator("DATABASE_URL")
    @classmethod
    def _resolve_sqlite_url(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            return value
        raw = value[len("sqlite:///"):]
        if raw == ":memory:" or raw.startswith("file:"):
            return value
        # Treat relative SQLite paths as relative to backend/, regardless of launch cwd.
        is_windows_absolute = bool(re.match(r"^[A-Za-z]:[\\/]", raw))
        if not Path(raw).is_absolute() and not is_windows_absolute:
            raw = str((_BACKEND_DIR / raw).resolve())
        return "sqlite:///" + raw

    # ── Helpers ──────────────────────────────────────────────────────
    @property
    def effective_api_key(self) -> str:
        """Return the single supported Meta credential setting."""
        return self.MODEL_API_KEY.get_secret_value()

    @property
    def meta_configured(self) -> bool:
        """True when a non-empty API key is present."""
        return bool(self.effective_api_key)

    def validate_for_live_mode(self) -> Optional[str]:
        """Return an error message if live mode cannot work, else None."""
        if self.DEMO_MODE:
            return None
        if not self.effective_api_key:
            return (
                "MODEL_API_KEY is required when DEMO_MODE is False. "
                "Set DEMO_MODE=true or provide a valid API key in backend/.env"
            )
        return None

    def safe_dict(self) -> dict:
        """Return config as a dict with secrets redacted."""
        d = self.model_dump()
        if d.get("MODEL_API_KEY"):
            d["MODEL_API_KEY"] = "***redacted***"
        if d.get("GEMINI_API_KEY"):
            d["GEMINI_API_KEY"] = "***redacted***"
        if "DATABASE_URL" in d and "://" in d["DATABASE_URL"]:
            parts = d["DATABASE_URL"].split("@")
            if len(parts) > 1:
                d["DATABASE_URL"] = "***redacted***@" + parts[-1]
        return d

    def __repr__(self) -> str:
        return f"Settings({self.safe_dict()})"


# ── Module-level singleton ─────────────────────────────────────────────
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the cached Settings instance (created on first call)."""
    global _settings
    if _settings is None:
        _settings = Settings()
        error = _settings.validate_for_live_mode()
        if error:
            logger.warning("Configuration warning: %s", error)
    return _settings


def set_settings(settings: Settings) -> None:
    """Install settings explicitly, primarily for isolated tests and app factories."""
    global _settings
    _settings = settings


def reset_settings() -> None:
    """Reset settings singleton (used in unit tests)."""
    global _settings
    _settings = None
