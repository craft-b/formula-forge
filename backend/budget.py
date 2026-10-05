"""In-process token budget (audit finding F4).

A minimal, thread-safe daily token budget with three caps: global, per client
address, and per session. It reserves an estimate up front (before the LLM
call) so a burst of requests cannot blow the budget between accounting points.
Resets at UTC day rollover.

Why both a client and a session cap: the session id is client-supplied, so a
caller that omits it or sends a fresh one per request gets a fresh session
allowance every time. The session cap bounds one conversation; only the client
cap bounds one caller. (Behind a proxy the client address is only the caller's
if uvicorn trusts the forwarded headers — see FORWARDED_ALLOW_IPS in the README.)

Deliberately in-process for Phase A (matches the single-instance deployment).
Phase B moves the counters to Redis so the caps hold across replicas — `reserve`
is the interface that adapter will implement.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from typing import Optional


class TokenBudget:
    def __init__(self, global_daily: int, session_daily: int,
                 client_daily: Optional[int] = None):
        self.global_daily = global_daily
        self.session_daily = session_daily
        self.client_daily = client_daily
        self._day = self._today()
        self._global_used = 0
        self._session_used: dict[str, int] = {}
        self._client_used: dict[str, int] = {}
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
            self._client_used = {}

    def reserve(self, session_id: str, est_tokens: int,
                client: Optional[str] = None) -> bool:
        """Atomically admit and consume `est_tokens`, or refuse.

        Check and consume happen under one lock. A separate check-then-record
        pair leaves a gap in which concurrent callers all pass the check before
        any of them consumes — the exact burst this class exists to prevent —
        and whether that gap is open would depend on how the caller happens to
        be scheduled. Here admission is atomic regardless.
        """
        with self._lock:
            self._roll_if_new_day()
            if self._global_used + est_tokens > self.global_daily:
                return False
            if self._session_used.get(session_id, 0) + est_tokens > self.session_daily:
                return False
            if (client is not None and self.client_daily is not None
                    and self._client_used.get(client, 0) + est_tokens > self.client_daily):
                return False
            self._global_used += est_tokens
            self._session_used[session_id] = (
                self._session_used.get(session_id, 0) + est_tokens)
            if client is not None:
                self._client_used[client] = self._client_used.get(client, 0) + est_tokens
            return True

    def usage(self, session_id: str) -> tuple[int, int]:
        """(session_used, global_used) — for diagnostics/telemetry."""
        with self._lock:
            self._roll_if_new_day()
            return self._session_used.get(session_id, 0), self._global_used

    def client_usage(self, client: str) -> int:
        with self._lock:
            self._roll_if_new_day()
            return self._client_used.get(client, 0)


def estimate_tokens(text: str, reserve_output: int = 800) -> int:
    """Rough token estimate: ~4 chars/token for input plus an output reserve.

    Intentionally conservative — over-estimating protects the budget. Phase B
    can replace this with exact provider usage metadata.
    """
    return max(1, len(text) // 4) + reserve_output
