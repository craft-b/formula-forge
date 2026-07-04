"""LLM provider layer (ports-and-adapters).

`build_chat_model` is the port: given a provider name it returns a LangChain
chat model (the adapter). Adding a provider means adding one constructor to
`_PROVIDERS` — no changes anywhere else (open/closed). `get_llm` composes a
primary model with a fallback model via LangChain's native `with_fallbacks`, so
a transient primary failure degrades gracefully to the fallback instead of
erroring the request (spec §2.3 reliability).

Honesty note (audit finding F5): the OpenAI and Anthropic adapters are real but
require their SDKs (`langchain-openai` / `langchain-anthropic`) to be installed.
Groq ships as the working default; the others raise a clear, actionable error if
selected without their package rather than pretending to work.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_TEMPERATURE = 0.3
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_FALLBACK_MODEL = "llama-3.1-8b-instant"


def _build_groq(model: str, temperature: float):
    from langchain_groq import ChatGroq
    return ChatGroq(model=model, temperature=temperature)


def _build_openai(model: str, temperature: float):
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "LLM_PROVIDER=openai requires `pip install langchain-openai` and OPENAI_API_KEY."
        ) from exc
    return ChatOpenAI(model=model, temperature=temperature)


def _build_anthropic(model: str, temperature: float):
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "LLM_PROVIDER=anthropic requires `pip install langchain-anthropic` and ANTHROPIC_API_KEY."
        ) from exc
    return ChatAnthropic(model=model, temperature=temperature)


# Provider registry (the adapter table). Extend here to add a provider.
_PROVIDERS = {
    "groq": _build_groq,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
}


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def build_chat_model(provider: str, model: str, temperature: float = DEFAULT_TEMPERATURE):
    """The port: construct a LangChain chat model for `provider`."""
    key = provider.lower()
    if key not in _PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider {provider!r}. Available: {available_providers()}."
        )
    return _PROVIDERS[key](model, temperature)


def _model_for(provider: str) -> str:
    """Resolve the model id for a provider from the environment."""
    if provider.lower() == "groq":
        return os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    model = os.getenv("LLM_MODEL")
    if not model:
        raise ValueError(
            f"LLM_PROVIDER={provider} requires LLM_MODEL to be set in the environment."
        )
    return model


def get_llm():
    """Return the configured chat model, primary with a fallback when enabled.

    temperature is intentionally low — formulation output should be grounded and
    reproducible, not creative. Set ENABLE_LLM_FALLBACK=false to disable the
    fallback chain (e.g. in tests or single-model deployments).
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    primary = build_chat_model(provider, _model_for(provider), DEFAULT_TEMPERATURE)

    if os.getenv("ENABLE_LLM_FALLBACK", "true").lower() != "true":
        return primary

    fb_provider = os.getenv("FALLBACK_PROVIDER", "groq").lower()
    fb_model = os.getenv("FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
    # Skip a pointless fallback that is identical to the primary.
    if fb_provider == provider and fb_model == _model_for(provider):
        return primary

    fallback = build_chat_model(fb_provider, fb_model, DEFAULT_TEMPERATURE)
    return primary.with_fallbacks([fallback])
