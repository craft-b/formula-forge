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


# ── Model ids ─────────────────────────────────────────────────────────────────
# Defined here because two places need them — the typed Settings below, which
# /health and /api/meta report from, and llm.py, which builds the client that
# actually calls the model. They used to be declared separately in both, with
# different values: with GROQ_MODEL unset the process called openai/gpt-oss-120b
# while /health and /api/meta reported llama-3.3-70b-versatile, and the startup
# availability check verified a model the process would never call. That is the
# same failure mode the note below describes, arriving by a different route.
#
# Both previous defaults — llama-3.3-70b-versatile and llama-3.1-8b-instant —
# were retired by Groq and now return 404 model_not_found. That took production
# down silently: /health does not call the model, so it reported "ok" against a
# model that no longer existed, and every test passed because they all mock the
# LLM. The live eval found it on its first real run.
#
# The lesson is in the pairing, not the names: a primary and a fallback from the
# same family retire together, so the fallback chain fell into the same hole.
#
# These two are ALSO the same family, and that is a known, accepted risk rather
# than an oversight. The account's model list was checked: of 14 models, only
# these two can do this job. qwen/qwen3.6-27b cannot hold JSON mode, and
# qwen/qwen3.8-27b rejects a formulation prompt as too large on this tier; the
# rest are speech, TTS, classifiers or agentic systems. So gpt-oss-120b/20b is
# not the safest available pairing — it is the only working one.
#
# What actually mitigates the risk is therefore not diversity but detection:
# llm.verify_model_available checks the configured id at startup, so the next
# retirement fails readiness loudly instead of hiding behind a green /health.
# If a second family that can hold JSON mode at this prompt size becomes
# available, the fallback should move to it.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_FALLBACK_MODEL = "openai/gpt-oss-20b"


class Settings(BaseSettings):
    """12-factor configuration. Field names map to upper-case env vars."""

    model_config = SettingsConfigDict(extra="ignore")

    # Service identity — surfaced by the /health readiness probe so a deployed
    # container can be matched to the build it is running. Override with
    # APP_VERSION (e.g. a git SHA stamped at image build time).
    app_version: str = "1.0.0"

    # LLM provider / fallback. Model ids come from the module-level constants
    # above so that this object and llm.py cannot disagree about which model the
    # process is running — they did, and /health reported the wrong one.
    llm_provider: str = "groq"
    groq_model: str = DEFAULT_GROQ_MODEL
    enable_llm_fallback: bool = True
    fallback_provider: str = "groq"
    fallback_model: str = DEFAULT_FALLBACK_MODEL

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
