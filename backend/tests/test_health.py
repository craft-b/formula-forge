"""Readiness probe: healthy and degraded paths (F19 operability).

The probe must be honest in both directions — 200 only when this instance can
actually serve a formulation request, 503 when a critical dependency is gone —
and it must never leak the API key or any fragment of it.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from main import app

_DEPENDENCIES = {"llm_client", "agent_graph", "ingredient_library"}


# ── Healthy path ──────────────────────────────────────────────────────────────

class TestHealthy:
    def test_returns_200_and_ok_status(self):
        with TestClient(app) as client:
            r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_reports_version_and_model(self):
        with TestClient(app) as client:
            body = client.get("/health").json()
        assert body["version"] == main.settings.app_version
        assert body["model"] == main.settings.groq_model  # groq is the default provider

    def test_every_dependency_reported_ok(self):
        with TestClient(app) as client:
            deps = client.get("/health").json()["dependencies"]
        assert set(deps) == _DEPENDENCIES
        assert all(d["status"] == "ok" for d in deps.values())

    def test_ingredient_library_probe_reports_real_dataset(self):
        from domain import get_repository
        with TestClient(app) as client:
            detail = client.get("/health").json()["dependencies"]["ingredient_library"]["detail"]
        assert str(len(get_repository().ingredients)) in detail


# ── Degraded paths → 503 ──────────────────────────────────────────────────────

class TestDegraded:
    def test_missing_api_key_is_503(self, monkeypatch):
        # Note the boot-time caveat: graph.py calls get_llm() at import, and
        # ChatGroq raises groq.GroqError when GROQ_API_KEY is unset, so a
        # container started without a key crash-loops rather than serving a 503.
        # This branch covers the key going away *after* a successful import
        # (env rewritten in-process) and keeps the probe fail-closed either way.
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with TestClient(app) as client:
            r = client.get("/health")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "unavailable"
        assert body["dependencies"]["llm_client"]["status"] == "unavailable"
        # Unrelated dependencies stay honest rather than cascading.
        assert body["dependencies"]["agent_graph"]["status"] == "ok"

    def test_unloaded_graph_is_503(self):
        with patch.object(main, "agent", None):
            with TestClient(app) as client:
                r = client.get("/health")
        assert r.status_code == 503
        assert r.json()["dependencies"]["agent_graph"]["status"] == "unavailable"

    def test_uninitialized_chat_model_is_503(self):
        with patch.object(main, "formula_llm", None):
            with TestClient(app) as client:
                r = client.get("/health")
        assert r.status_code == 503
        assert r.json()["dependencies"]["llm_client"]["status"] == "unavailable"

    def test_unreadable_ingredient_library_is_503(self):
        with patch("domain.get_repository", side_effect=OSError("no such file")):
            with TestClient(app) as client:
                r = client.get("/health")
        assert r.status_code == 503
        dep = r.json()["dependencies"]["ingredient_library"]
        assert dep["status"] == "unavailable"
        assert "OSError" in dep["detail"]  # class name only, no file paths


# ── The key must never appear in the body ─────────────────────────────────────

class TestNoSecretLeakage:
    def test_key_fingerprint_and_key_absent_from_response(self, monkeypatch):
        secret = "gsk_liveKeyMaterial1234567890abcdef"
        monkeypatch.setenv("GROQ_API_KEY", secret)
        with TestClient(app) as client:
            raw = client.get("/health").text
        from config import groq_key_fingerprint
        assert secret not in raw
        assert groq_key_fingerprint() not in raw
        # No substring of the key long enough to be useful, either.
        assert secret[:7] not in raw
        assert secret[-4:] not in raw

    def test_probe_makes_no_llm_call(self):
        # Readiness must not spend tokens: nothing on the chat path is invoked.
        with patch.object(main, "formula_llm") as model, patch.object(main, "agent") as graph:
            with TestClient(app) as client:
                client.get("/health")
        model.invoke.assert_not_called()
        graph.astream_events.assert_not_called()


# ── Model existence (the outage /health could not see) ────────────────────────

class TestModelAvailabilityCheck:
    """A configured model that no longer exists must not read as healthy.

    Groq retired llama-3.3-70b-versatile and llama-3.1-8b-instant. /health kept
    reporting "ok" because its probes take no network call by design, so it was
    answering "is a client constructed" when the question that mattered was
    "does this model still exist". Production 404'd on every request behind a
    green probe.
    """

    @staticmethod
    def _groq_returning(model_ids):
        class _Model:
            def __init__(self, mid):
                self.id = mid

        class _Models:
            def list(self):
                return type("R", (), {"data": [_Model(m) for m in model_ids]})()

        class _Client:
            models = _Models()

        return lambda *a, **k: _Client()

    def test_a_present_model_verifies(self, monkeypatch):
        import llm

        monkeypatch.setenv("VERIFY_MODEL_ON_STARTUP", "true")
        monkeypatch.setattr("groq.Groq", self._groq_returning(["openai/gpt-oss-120b"]))
        status, detail = llm.verify_model_available("openai/gpt-oss-120b")
        assert status == "ok"
        assert "openai/gpt-oss-120b" in detail

    def test_a_retired_model_is_reported_missing(self, monkeypatch):
        """The actual outage, reproduced."""
        import llm

        monkeypatch.setenv("VERIFY_MODEL_ON_STARTUP", "true")
        monkeypatch.setattr("groq.Groq",
                            self._groq_returning(["openai/gpt-oss-120b",
                                                  "openai/gpt-oss-20b"]))
        status, detail = llm.verify_model_available("llama-3.3-70b-versatile")
        assert status == "missing"
        assert "404" in detail

    def test_the_hint_names_alternatives_from_the_same_provider(self, monkeypatch):
        import llm

        monkeypatch.setenv("VERIFY_MODEL_ON_STARTUP", "true")
        monkeypatch.setattr("groq.Groq",
                            self._groq_returning(["openai/gpt-oss-120b",
                                                  "openai/gpt-oss-20b",
                                                  "qwen/qwen3.6-27b"]))
        _, detail = llm.verify_model_available("openai/gpt-oss-999b")
        assert "openai/gpt-oss-120b" in detail
        assert "qwen/qwen3.6-27b" not in detail, "only same-provider suggestions"

    def test_a_verification_failure_never_reports_missing(self, monkeypatch):
        """A flaky metadata call must not take a working instance out of rotation.

        Only a definitive absence is 'missing'; anything else is 'unverified'.
        """
        import llm

        monkeypatch.setenv("VERIFY_MODEL_ON_STARTUP", "true")

        def _boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr("groq.Groq", _boom)
        status, detail = llm.verify_model_available("openai/gpt-oss-120b")
        assert status == "unverified"
        assert "RuntimeError" in detail

    def test_verification_can_be_switched_off(self, monkeypatch):
        import llm

        monkeypatch.setenv("VERIFY_MODEL_ON_STARTUP", "false")

        def _must_not_be_called(*a, **k):
            raise AssertionError("no network call when verification is disabled")

        monkeypatch.setattr("groq.Groq", _must_not_be_called)
        status, _ = llm.verify_model_available("anything")
        assert status == "unverified"

    def test_the_probe_turns_a_missing_model_into_503(self, monkeypatch):
        """End of the chain: a missing model must fail readiness, not pass it."""
        import main
        from fastapi.testclient import TestClient

        monkeypatch.setattr(main.app.state, "model_check",
                            ("missing", "Model 'gone' does not exist — 404."),
                            raising=False)
        with TestClient(main.app) as client:
            # TestClient runs lifespan, which would overwrite model_check.
            main.app.state.model_check = ("missing", "Model 'gone' does not exist — 404.")
            body = client.get("/health").json()
        assert body["dependencies"]["llm_client"]["status"] == "unavailable"
        assert body["status"] != "ok"
