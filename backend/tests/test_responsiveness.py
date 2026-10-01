"""A slow or stalled provider call must not stall the instance (review H2, H3).

The iteration and repair paths call the provider synchronously. Run inline in
the async SSE generator, each one held the event loop for the whole round trip:
/health went from 8 ms to 1.6 s while a single iteration was in flight. And the
provider clients had no timeout, so a call that never answered never ended.
"""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import patch

import httpx
import pytest

import main
from llm import build_chat_model
from tests.test_iteration import _GOOD

_SLOW_S = 1.0


class TestProviderCallsAreBounded:
    def test_default_timeout_and_retries(self, monkeypatch):
        monkeypatch.delenv("LLM_TIMEOUT_S", raising=False)
        monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
        model = build_chat_model("groq", "openai/gpt-oss-120b")
        assert model.request_timeout == 30.0
        assert model.max_retries == 1

    def test_limits_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT_S", "12")
        monkeypatch.setenv("LLM_MAX_RETRIES", "0")
        model = build_chat_model("groq", "openai/gpt-oss-120b")
        assert model.request_timeout == 12.0
        assert model.max_retries == 0


def _slow_iterate(*args, **kwargs):
    time.sleep(_SLOW_S)  # a blocking provider round trip
    return json.dumps(_GOOD)


@pytest.mark.asyncio
async def test_health_answers_while_an_iteration_is_in_flight():
    main.last_formula_store["s-slow"] = "X [standard]: Sucrose (table sugar) 100%"
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("main.iterate_formula", side_effect=_slow_iterate):
            # The clock starts before the chat request is dispatched: when the
            # provider call blocks the loop, it does so while this coroutine is
            # parked, and the stall only shows up in wall time measured across it.
            started = time.perf_counter()
            chat = asyncio.create_task(client.post(
                "/api/chat", json={"message": "make it sweeter", "session_id": "s-slow"}))
            await asyncio.sleep(0.05)  # let the iteration reach the provider call
            health = await client.get("/health")
            elapsed = time.perf_counter() - started
            reply = await chat
    assert health.status_code == 200
    assert elapsed < _SLOW_S / 2, f"/health waited {elapsed:.2f}s behind the provider call"
    assert '"type": "formula"' in reply.text
