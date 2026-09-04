"""A5: honest provider layer (LLMPort adapters + fallback chain) — F5.

Two things these tests deliberately avoid.

They do not hardcode model ids. An earlier version named
`llama-3.3-70b-versatile` and `llama-3.1-8b-instant`, and kept passing after
Groq retired both — they only ever constructed objects, never called them. A
test naming a dead model teaches nothing and rots silently, so the ids come
from `llm`'s own constants and follow whatever it is configured to use.

They also do not construct a real `ChatGroq` unless that is the point of the
test. Each construction costs ~3s building an HTTP client, and four of them
were over half the suite's runtime. Composition logic — which model is chosen,
whether a fallback is attached — is exercised against a stub adapter instead.
One test still builds the real thing, because something has to prove the
adapter is wired to the actual SDK.
"""
from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableLambda

import llm


@pytest.fixture
def stub_providers(monkeypatch):
    """Replace the adapter table with cheap Runnables, recording the calls.

    Keeps `get_llm`'s branching under test without paying for an SDK client.
    """
    built: list[tuple[str, str]] = []

    def _make(provider: str):
        def _factory(model: str, temperature: float):
            built.append((provider, model))
            stub = RunnableLambda(lambda x: x)
            stub.model_name = model          # type: ignore[attr-defined]
            stub.provider_name = provider    # type: ignore[attr-defined]
            return stub
        return _factory

    monkeypatch.setattr(
        llm, "_PROVIDERS",
        {name: _make(name) for name in ("groq", "openai", "anthropic")})
    return built


# ── the registry ──────────────────────────────────────────────────────────────

def test_registry_lists_known_providers():
    assert set(llm.available_providers()) == {"groq", "openai", "anthropic"}


def test_unknown_provider_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        llm.build_chat_model("mistral", "whatever")


def test_build_groq_returns_a_real_chatgroq():
    """The one test that pays for a real construction.

    Everything else stubs the adapter table, so without this nothing would
    notice if the groq entry stopped returning a usable ChatGroq.
    """
    model = llm.build_chat_model("groq", llm.DEFAULT_GROQ_MODEL)
    assert hasattr(model, "invoke")
    assert type(model).__name__ == "ChatGroq"


# ── composition ───────────────────────────────────────────────────────────────

def test_get_llm_composes_fallback_by_default(monkeypatch, stub_providers):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("ENABLE_LLM_FALLBACK", "true")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("FALLBACK_MODEL", raising=False)
    model = llm.get_llm()
    assert hasattr(model, "fallbacks")
    assert len(model.fallbacks) == 1
    assert stub_providers == [
        ("groq", llm.DEFAULT_GROQ_MODEL),
        ("groq", llm.DEFAULT_FALLBACK_MODEL),
    ]


def test_get_llm_without_fallback_returns_primary(monkeypatch, stub_providers):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("ENABLE_LLM_FALLBACK", "false")
    model = llm.get_llm()
    assert not hasattr(model, "fallbacks")
    assert len(stub_providers) == 1


def test_identical_fallback_is_skipped(monkeypatch, stub_providers):
    """A fallback to the same model is a retry that cannot help."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "some-model")
    monkeypatch.setenv("ENABLE_LLM_FALLBACK", "true")
    monkeypatch.setenv("FALLBACK_PROVIDER", "groq")
    monkeypatch.setenv("FALLBACK_MODEL", "some-model")
    model = llm.get_llm()
    assert not hasattr(model, "fallbacks")
    assert stub_providers == [("groq", "some-model")]


def test_env_overrides_the_default_model(monkeypatch, stub_providers):
    """Render sets GROQ_MODEL; config must win over the compiled-in default."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "chosen-by-operator")
    monkeypatch.setenv("ENABLE_LLM_FALLBACK", "false")
    llm.get_llm()
    assert stub_providers == [("groq", "chosen-by-operator")]


def test_non_groq_provider_requires_model_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="requires LLM_MODEL"):
        llm.get_llm()


# ── the lesson from the outage, as a test ─────────────────────────

def test_the_fallback_is_not_the_primary():
    """A fallback identical to the primary is the same bet placed twice.

    This is the weaker half of the lesson. The stronger half - that the two
    should come from different families, because a vendor clearing out a
    family takes every member - is deliberately NOT asserted here, because it
    is not currently true and cannot be made true on this account. Of its 14
    models only gpt-oss-120b and gpt-oss-20b can hold JSON mode at this
    prompt size, and they are one family. Asserting the ideal would mean
    either a permanently failing test or a fake fix.

    See llm.py's note: the accepted mitigation is startup verification making
    a retirement loud, not diversity that is unavailable.
    """
    assert llm.DEFAULT_GROQ_MODEL != llm.DEFAULT_FALLBACK_MODEL


def test_a_missing_model_is_reported_as_missing_not_unverified(monkeypatch):
    """The detection that stands in for family diversity must actually work."""
    monkeypatch.setenv("VERIFY_MODEL_ON_STARTUP", "true")

    class _Models:
        def list(self):
            return type("R", (), {"data": [type("M", (), {"id": "openai/gpt-oss-120b"})()]})()

    monkeypatch.setattr("groq.Groq", lambda *a, **k: type("C", (), {"models": _Models()})())
    status, detail = llm.verify_model_available("llama-3.3-70b-versatile")
    assert status == "missing"
    assert "404" in detail
