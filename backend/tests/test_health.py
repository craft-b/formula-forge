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
