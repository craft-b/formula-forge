"""
A misconfigured proxy does not fail. It merges every caller into one.

`get_remote_address()` reads `request.client.host`. Behind a proxy that uvicorn
has not been told to trust, that is the proxy's address for every visitor on
Earth, so the rate limit and `CLIENT_DAILY_TOKENS` keep working, report
nothing, and have silently become a second global cap. The README has carried
that caveat under "deliberately not built" for as long as the cap has existed;
a caveat in a document is not a signal from a running process.

The detector is empirical rather than a guess about the host: when uvicorn
trusts the proxy it rewrites `client.host` to the first `X-Forwarded-For`
entry, so the two disagreeing *is* the untrusted case, on Render or anywhere
else.
"""

import logging

import pytest

from observability import (
    _reset_proxy_warning_for_tests,
    proxy_headers_untrusted,
    warn_once_if_proxy_untrusted,
)


@pytest.fixture(autouse=True)
def _fresh_warning_state():
    _reset_proxy_warning_for_tests()
    yield
    _reset_proxy_warning_for_tests()


class TestDetection:
    def test_untrusted_proxy_is_detected(self):
        # uvicorn left client.host as the proxy; the header carries the caller.
        assert proxy_headers_untrusted("10.0.0.7", "203.0.113.9") is True

    def test_trusted_proxy_is_not_flagged(self):
        # uvicorn rewrote client.host to the forwarded caller, which is the
        # configuration we are asking for -- warning here would train the
        # reader to ignore the warning.
        assert proxy_headers_untrusted("203.0.113.9", "203.0.113.9") is False

    def test_direct_connection_is_not_flagged(self):
        # No proxy in front: nothing to trust, nothing to warn about.
        assert proxy_headers_untrusted("203.0.113.9", None) is False
        assert proxy_headers_untrusted("127.0.0.1", "") is False

    def test_uses_the_first_hop_of_a_chain(self):
        # X-Forwarded-For accumulates left to right, original client first,
        # which is also the entry uvicorn adopts.
        assert proxy_headers_untrusted("203.0.113.9", "203.0.113.9, 10.0.0.7") is False
        assert proxy_headers_untrusted("10.0.0.7", "203.0.113.9, 10.0.0.1") is True

    def test_tolerates_whitespace_and_missing_client(self):
        assert proxy_headers_untrusted("203.0.113.9", "  203.0.113.9 , 10.0.0.7") is False
        # ASGI permits no client at all; absence is not evidence of a problem.
        assert proxy_headers_untrusted(None, "203.0.113.9") is False
        assert proxy_headers_untrusted("10.0.0.7", "   ") is False


class TestWarning:
    def test_warns_once_and_says_what_is_broken(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert warn_once_if_proxy_untrusted("10.0.0.7", "203.0.113.9") is True

        message = caplog.text
        # The operator needs the fix, not just the symptom.
        assert "FORWARDED_ALLOW_IPS" in message
        assert "CLIENT_DAILY_TOKENS" in message
        # And both addresses, so the diagnosis is checkable rather than asserted.
        assert "203.0.113.9" in message
        assert "10.0.0.7" in message

    def test_does_not_repeat_on_every_request(self, caplog):
        # This runs in the middleware, so on a busy process an unthrottled
        # warning would be the loudest thing in the log and the first thing
        # filtered out.
        assert warn_once_if_proxy_untrusted("10.0.0.7", "203.0.113.9") is True
        # caplog accumulates for the whole test, and the first call above is
        # supposed to log -- without this the assertion below fails on the
        # warning it is meant to permit.
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            for _ in range(50):
                assert warn_once_if_proxy_untrusted("10.0.0.7", "203.0.113.9") is False
        assert caplog.text == ""

    def test_silent_when_correctly_configured(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert warn_once_if_proxy_untrusted("203.0.113.9", "203.0.113.9") is False
            assert warn_once_if_proxy_untrusted("203.0.113.9", None) is False
        assert caplog.text == ""


class TestWiredIntoTheRequestPath:
    def test_middleware_calls_it(self):
        # A detector nothing invokes is worse than none: it reads as covered.
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        assert "warn_once_if_proxy_untrusted(" in source
        # Inside the per-request middleware, not at import, because the
        # evidence only exists on a real request.
        middleware = source.split("async def request_id_middleware")[1].split("\n\n\n")[0]
        assert "warn_once_if_proxy_untrusted(" in middleware
        assert "x-forwarded-for" in middleware
