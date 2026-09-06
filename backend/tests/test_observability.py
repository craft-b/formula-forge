"""Correlation ids: every response carries one, especially the ones that fail.

The README's operability claim is that a client-reported failure can be traced
to its log lines. That only holds if the id survives the failure path, and it
did not: the middleware reset the contextvar in a `finally`, which runs before
the handler that turns the exception into a 500. So the 500 went out with no
X-Request-ID header, and the traceback was logged with no id — the one request
anyone would report was the one request that could not be traced.

Nothing covered this, which is why it survived. These tests pin both halves.
"""
from __future__ import annotations

import io
import logging

import pytest
from fastapi.testclient import TestClient

import domain
import main
from observability import _RequestIdFilter


@pytest.fixture
def client():
    # raise_server_exceptions=False so the 500 comes back as a response rather
    # than propagating into the test, which is what a real client sees.
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def captured_logs():
    """Attach a handler that renders the request id the same way production does."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("[%(request_id)s] %(message)s"))
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield buf
    finally:
        root.removeHandler(handler)


class TestRequestIdOnSuccess:
    def test_echoes_inbound_id(self, client):
        r = client.get("/api/meta", headers={"X-Request-ID": "inbound-abc123"})
        assert r.status_code == 200
        assert r.headers["X-Request-ID"] == "inbound-abc123"

    def test_mints_an_id_when_absent(self, client):
        r = client.get("/api/meta")
        assert r.status_code == 200
        minted = r.headers.get("X-Request-ID")
        assert minted and len(minted) == 12

    def test_ids_differ_between_requests(self, client):
        first = client.get("/api/meta").headers["X-Request-ID"]
        second = client.get("/api/meta").headers["X-Request-ID"]
        assert first != second


class TestRequestIdSurvivesFailure:
    """The regression. Each of these failed before the middleware was fixed."""

    @pytest.fixture
    def failing_meta(self, monkeypatch):
        # /api/meta resolves the repository at call time, so making that raise
        # produces a genuine unhandled error through the real middleware stack
        # without registering a throwaway route on the shared app.
        def boom():
            raise RuntimeError("simulated repository failure")

        monkeypatch.setattr(domain, "get_repository", boom)

    def test_500_carries_the_inbound_id(self, client, failing_meta):
        r = client.get("/api/meta", headers={"X-Request-ID": "failpath-xyz"})
        assert r.status_code == 500
        assert r.headers["X-Request-ID"] == "failpath-xyz"

    def test_500_body_carries_the_id_and_the_exception_class(self, client, failing_meta):
        r = client.get("/api/meta", headers={"X-Request-ID": "failpath-body"})
        body = r.json()
        assert body["request_id"] == "failpath-body"
        assert body["error"] == "RuntimeError"

    def test_500_body_does_not_leak_the_exception_message(self, client, failing_meta):
        r = client.get("/api/meta", headers={"X-Request-ID": "failpath-leak"})
        assert "simulated repository failure" not in r.text

    def test_failure_is_logged_with_the_id_bound(self, client, failing_meta, captured_logs):
        client.get("/api/meta", headers={"X-Request-ID": "failpath-log"})
        assert "failpath-log" in captured_logs.getvalue()
