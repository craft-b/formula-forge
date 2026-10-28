"""Structured logging with per-request correlation ids (audit finding F19).

Every log line carries a request id so a single request can be traced through
the logs. In Phase B this contextvar is also where an OpenTelemetry trace id
would be attached (spec §2.3 maintainability).
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Proxy trust ──────────────────────────────────────────────────────────────

_proxy_warning_emitted = False


def proxy_headers_untrusted(client_host: str | None, forwarded_for: str | None) -> bool:
    """
    True when a proxy is forwarding the caller's address and uvicorn is ignoring it.

    When uvicorn is told to trust the proxy (``--proxy-headers`` with the peer
    inside ``FORWARDED_ALLOW_IPS``) it rewrites ``request.client.host`` to the
    first entry of ``X-Forwarded-For``. When it is not, ``client.host`` stays
    the proxy's own address while the header still carries the real caller --
    so the two disagreeing is the signal, and it needs no guess about which
    host this is running on.

    This matters because every per-address control degrades silently without
    it. ``get_remote_address()`` reads ``request.client.host``, so behind an
    untrusted proxy the rate limit and the per-address token cap key every
    visitor in the world to one value: they keep working, they report nothing,
    and they have quietly become a second global cap.
    """
    if not forwarded_for:
        return False
    first_hop = forwarded_for.split(",")[0].strip()
    if not first_hop or not client_host:
        return False
    return client_host != first_hop


def warn_once_if_proxy_untrusted(client_host: str | None, forwarded_for: str | None) -> bool:
    """Log the above at most once per process. Returns whether it logged."""
    global _proxy_warning_emitted
    if _proxy_warning_emitted or not proxy_headers_untrusted(client_host, forwarded_for):
        return False
    _proxy_warning_emitted = True
    logging.getLogger(__name__).warning(
        "Per-address limits are not seeing real callers. X-Forwarded-For says %s "
        "but this process sees %s, so uvicorn is not trusting the proxy: the rate "
        "limit and CLIENT_DAILY_TOKENS are keyed to the proxy and shared by every "
        "visitor. Set FORWARDED_ALLOW_IPS=* where this app is reachable only "
        "through the proxy.",
        forwarded_for.split(",")[0].strip() if forwarded_for else "?",
        client_host,
    )
    return True


def _reset_proxy_warning_for_tests() -> None:
    global _proxy_warning_emitted
    _proxy_warning_emitted = False
