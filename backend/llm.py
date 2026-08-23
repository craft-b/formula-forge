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

import config  # noqa: F401  # importing loads .env once (single load point, F15)

DEFAULT_TEMPERATURE = 0.3

# Both previous defaults — llama-3.3-70b-versatile and llama-3.1-8b-instant —
# were retired by Groq and now return 404 model_not_found. That took production
# down silently: /health does not call the model, so it reported "ok" against a
# model that no longer existed, and every one of 208 tests passed because they
# all mock the LLM. The live eval found it on its first real run.
#
# The lesson is in the pairing, not the names: a primary and a fallback from the
# same family retire together, so the fallback chain fell into the same hole.
# These two are from different families for that reason, and both support the
# JSON mode formula generation depends on. `verify_model_available` checks the
# configured id at startup so the next retirement is loud.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_FALLBACK_MODEL = "openai/gpt-oss-20b"


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


def verify_model_available(model: str) -> tuple[str, str]:
    """Does the configured model exist on this account? One call, at startup.

    Returns ``(status, detail)`` where status is ``ok``, ``missing`` or
    ``unverified``.

    This is deliberately *not* a chat completion and deliberately *not* run per
    readiness probe. The probes in main.py avoid network calls on purpose — a
    live call per probe would bill every uptime check and couple liveness to a
    third party's availability. But that rule is what let a retired model sit
    behind a green /health indefinitely, so the model list (metadata, no token
    spend) is fetched once at startup and the verdict cached.

    A failure to verify is reported as ``unverified``, never ``missing``. A
    flaky metadata endpoint or a key without the models scope must not take a
    working instance out of rotation — only a definitive absence should.

    ``VERIFY_MODEL_ON_STARTUP=false`` skips the call entirely. The test suite
    sets it: startup runs on every app fixture, and a network round trip there
    turned a 24-second suite into 86 seconds while making the tests depend on
    Groq being reachable. The function itself is tested directly instead.
    """
    if os.getenv("VERIFY_MODEL_ON_STARTUP", "true").strip().lower() != "true":
        return "unverified", "Startup model verification is disabled."
    try:
        from groq import Groq

        available = {m.id for m in Groq().models.list().data}
    except Exception as exc:  # noqa: BLE001 - never fail startup over a probe
        return "unverified", f"Could not list models ({type(exc).__name__})."
    if model in available:
        return "ok", f"Model {model!r} is available on this account."
    close = sorted(m for m in available if m.split("/")[0] == model.split("/")[0])
    hint = f" Available from the same provider: {', '.join(close)}." if close else ""
    return "missing", (
        f"Model {model!r} does not exist on this account — every generation "
        f"request will fail with 404.{hint}"
    )


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
