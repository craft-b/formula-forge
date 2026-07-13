"""Centralized configuration — the single `.env` load point (audit finding F15).

Importing this module is the one and only place `.env` is loaded. It populates
`os.environ`, so modules that read `os.getenv` at call time (e.g. llm.py, kept
dynamic for testability) and the typed `settings` object below both see one
consistent environment. This removes the previous double `load_dotenv()` and its
import-ordering trap between main.py and llm.py.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# Dashboard-pasted secrets routinely pick up stray whitespace or wrapping
# quotes that turn a valid key into an AuthenticationError. Normalize once,
# here at the single load point.
_raw_key = os.getenv("GROQ_API_KEY")
if _raw_key:
    os.environ["GROQ_API_KEY"] = _raw_key.strip().strip("\"'").strip()


def groq_key_fingerprint() -> str:
    """Safe-to-log identity of the key the process actually sees."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return "MISSING"
    return f"len={len(key)} prefix={key[:7]} suffix={key[-4:]}"


class Settings(BaseSettings):
    """12-factor configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(extra="ignore")

    # LLM provider / fallback
    llm_provider: str = "groq"
    groq_model: str = "llama-3.3-70b-versatile"
    enable_llm_fallback: bool = True
    fallback_provider: str = "groq"
    fallback_model: str = "llama-3.1-8b-instant"

    # Abuse controls
    allowed_origins: str = "http://localhost:5173,https://formula-forge-chi.vercel.app"
    chat_rate_limit: str = "30/minute"
    global_daily_tokens: int = 2_000_000
    session_daily_tokens: int = 50_000

    # Observability
    langchain_tracing_v2: bool = False
    log_level: str = "INFO"

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
