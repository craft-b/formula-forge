"""In-process token budget (audit finding F4).

A minimal, thread-safe daily token budget with a global cap and a per-session
cap. It reserves an estimate up front (before the LLM call) so a burst of
requests cannot blow the budget between accounting points. Resets at UTC day
rollover.

Deliberately in-process for Phase A (matches the single-instance deployment).
Phase B moves the counters to Redis so the cap holds across replicas — the
interface here (`allow` / `record`) is what that adapter will implement.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone


class TokenBudget:
    def __init__(self, global_daily: int, session_daily: int):
        self.global_daily = global_daily
        self.session_daily = session_daily
        self._day = self._today()
        self._global_used = 0
        self._session_used: dict[str, int] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> date:
        return datetime.now(timezone.utc).date()

    def _roll_if_new_day(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._global_used = 0
            self._session_used = {}

    def allow(self, session_id: str, est_tokens: int) -> bool:
        """True if `est_tokens` fit within both the global and session caps."""
        with self._lock:
            self._roll_if_new_day()
            if self._global_used + est_tokens > self.global_daily:
                return False
            if self._session_used.get(session_id, 0) + est_tokens > self.session_daily:
                return False
            return True

    def reserve(self, session_id: str, est_tokens: int) -> bool:
        """Atomically admit and consume `est_tokens`, or refuse. Use this to admit.

        `allow` followed by `record` is two lock acquisitions with a gap between
        them, so concurrent callers can all pass the check before any of them
        consumes anything — the exact burst this class documents itself as
        preventing. Today the one caller is an async endpoint with no await
        between the two calls, so the event loop cannot interleave and the gap is
        closed by scheduling accident rather than by design. Adding an await,
        making the endpoint sync so it runs in the threadpool, or calling this
        from a worker thread would each reopen it silently, and the budget's whole
        job is to fail safe.

        Check and consume happen under one lock here, so admission is atomic
        regardless of how the caller is scheduled.
        """
        with self._lock:
            self._roll_if_new_day()
            if self._global_used + est_tokens > self.global_daily:
                return False
            if self._session_used.get(session_id, 0) + est_tokens > self.session_daily:
                return False
            self._global_used += est_tokens
            self._session_used[session_id] = (
                self._session_used.get(session_id, 0) + est_tokens)
            return True

    def record(self, session_id: str, tokens: int) -> None:
        with self._lock:
            self._roll_if_new_day()
            self._global_used += tokens
            self._session_used[session_id] = self._session_used.get(session_id, 0) + tokens

    def usage(self, session_id: str) -> tuple[int, int]:
        """(session_used, global_used) — for diagnostics/telemetry."""
        with self._lock:
            self._roll_if_new_day()
            return self._session_used.get(session_id, 0), self._global_used


def estimate_tokens(text: str, reserve_output: int = 800) -> int:
    """Rough token estimate: ~4 chars/token for input plus an output reserve.

    Intentionally conservative — over-estimating protects the budget. Phase B
    can replace this with exact provider usage metadata.
    """
    return max(1, len(text) // 4) + reserve_output
