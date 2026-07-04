"""A5: honest provider layer (LLMPort adapters + fallback chain) — F5."""
from __future__ import annotations

import pytest

import llm


def test_registry_lists_known_providers():
    assert set(llm.available_providers()) == {"groq", "openai", "anthropic"}


def test_build_groq_returns_runnable():
    model = llm.build_chat_model("groq", "llama-3.3-70b-versatile")
    assert hasattr(model, "invoke")
    assert type(model).__name__ == "ChatGroq"


def test_unknown_provider_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        llm.build_chat_model("mistral", "whatever")


def test_get_llm_composes_fallback_by_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("ENABLE_LLM_FALLBACK", "true")
    monkeypatch.setenv("FALLBACK_MODEL", "llama-3.1-8b-instant")
    model = llm.get_llm()
    # RunnableWithFallbacks exposes a `.fallbacks` sequence.
    assert hasattr(model, "fallbacks")
    assert len(model.fallbacks) == 1


def test_get_llm_without_fallback_returns_primary(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("ENABLE_LLM_FALLBACK", "false")
    model = llm.get_llm()
    assert type(model).__name__ == "ChatGroq"


def test_identical_fallback_is_skipped(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("ENABLE_LLM_FALLBACK", "true")
    monkeypatch.setenv("FALLBACK_PROVIDER", "groq")
    monkeypatch.setenv("FALLBACK_MODEL", "llama-3.3-70b-versatile")
    model = llm.get_llm()
    assert type(model).__name__ == "ChatGroq"  # no pointless fallback


def test_non_groq_provider_requires_model_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="requires LLM_MODEL"):
        llm.get_llm()
