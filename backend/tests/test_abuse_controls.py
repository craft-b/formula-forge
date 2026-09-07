"""A4: abuse controls — CORS allowlist, rate limiting, token budget (F4)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import main
from budget import TokenBudget, estimate_tokens
from config import Settings
from main import app


# ── CORS allowlist ────────────────────────────────────────────────────────────

class TestCorsAllowlist:
    # These exercise Settings.origins, which is what main.ALLOWED_ORIGINS is
    # built from. main.py previously carried a byte-identical private copy that
    # nothing called, and these tests covered that copy — so they would have
    # stayed green while the live parser broke.
    def test_origins_splits_and_trims(self):
        assert Settings(allowed_origins="a, b ,c").origins == ["a", "b", "c"]

    def test_origins_drops_empty(self):
        assert Settings(allowed_origins="a,, ,b").origins == ["a", "b"]

    def test_no_wildcard_origin_configured(self):
        assert "*" not in main.ALLOWED_ORIGINS
        assert len(main.ALLOWED_ORIGINS) >= 1


# ── Token budget (unit) ───────────────────────────────────────────────────────

class TestReserveIsAtomic:
    """Admission must not over-admit when callers race.

    `allow` then `record` is check-then-act across two lock acquisitions: every
    thread can pass the check before any of them consumes. `reserve` does both
    under one lock, so the cap holds no matter how the callers are scheduled.
    """

    def _race(self, fn, threads: int, cap: int):
        import threading

        b = TokenBudget(global_daily=cap, session_daily=cap)
        barrier = threading.Barrier(threads)
        granted: list[bool] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()          # release everyone at once, maximising overlap
            ok = fn(b)
            with lock:
                granted.append(ok)

        ts = [threading.Thread(target=worker) for _ in range(threads)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        return b, sum(granted)

    def test_reserve_never_exceeds_the_cap_under_contention(self):
        cap, threads = 10, 60
        b, admitted = self._race(lambda b: b.reserve("s1", 1), threads=threads, cap=cap)
        assert admitted == cap, f"admitted {admitted} against a cap of {cap}"
        assert b.usage("s1") == (cap, cap)

    def test_reserve_consumes_exactly_what_it_admits(self):
        b = TokenBudget(global_daily=1000, session_daily=1000)
        assert b.reserve("s1", 400) is True
        assert b.usage("s1") == (400, 400)
        # Refused reservations must not consume.
        assert b.reserve("s1", 700) is False
        assert b.usage("s1") == (400, 400)


class TestTokenBudget:
    def test_estimate_scales_with_length(self):
        assert estimate_tokens("x" * 400, reserve_output=0) == 100

    def test_allows_within_caps(self):
        b = TokenBudget(global_daily=1000, session_daily=500)
        assert b.allow("s1", 400) is True

    def test_blocks_over_session_cap(self):
        b = TokenBudget(global_daily=10000, session_daily=500)
        b.record("s1", 400)
        assert b.allow("s1", 200) is False   # 400+200 > 500
        assert b.allow("s2", 200) is True    # different session

    def test_blocks_over_global_cap(self):
        b = TokenBudget(global_daily=500, session_daily=10000)
        b.record("s1", 400)
        assert b.allow("s2", 200) is False   # 400+200 > 500 global

    def test_day_rollover_resets(self):
        b = TokenBudget(global_daily=500, session_daily=500)
        b.record("s1", 500)
        assert b.allow("s1", 1) is False
        b._day = b._day.replace(year=b._day.year - 1)  # force stale day
        assert b.allow("s1", 500) is True    # rolled over -> reset


# ── Token budget (integration → 429) ──────────────────────────────────────────

@pytest.fixture
def formula_stream():
    class _Chunk:
        def __init__(self, c): self.content = c

    async def _stream(*a, **k):
        yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("hi")},
               "metadata": {"langgraph_node": "rag_agent"}}
    return _stream


def test_chat_returns_429_when_budget_exhausted(formula_stream):
    tiny = TokenBudget(global_daily=10, session_daily=10)  # anything real exceeds
    with patch("main.agent") as m, patch.object(main, "budget", tiny):
        m.astream_events = formula_stream
        with TestClient(app) as client:
            r = client.post("/api/chat", json={"message": "hello there"})
    assert r.status_code == 429
    assert "budget" in r.json()["error"].lower()


# ── Rate limiting (integration → 429) ─────────────────────────────────────────

def test_chat_rate_limited_after_threshold(formula_stream):
    with patch("main.agent") as m, patch.object(main, "CHAT_RATE_LIMIT", "3/minute"):
        m.astream_events = formula_stream
        with TestClient(app) as client:
            codes = [client.post("/api/chat", json={"message": "hi"}).status_code
                     for _ in range(5)]
    # Under a 3/minute cap, at least one of five rapid calls is rejected.
    assert 429 in codes
