"""Integration test for the prime directive (A2).

Asserts that the API's formula path cannot emit a formula without it having
passed through domain.validate_candidate — there is no G→user bypass — and that
LLM-supplied nutrition never reaches the client.
"""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch

import generation
import main


class _Chunk:
    def __init__(self, content: str):
        self.content = content


def _parse_sse(text: str) -> list[dict]:
    out = []
    for part in text.split("\n\n"):
        part = part.strip()
        if part.startswith("data: ") and part[6:] != "[DONE]":
            try:
                out.append(json.loads(part[6:]))
            except json.JSONDecodeError:
                pass
    return out


def _formula_stream_factory(payload: dict):
    async def _stream(*args, **kwargs):
        yield {"event": "on_chain_start", "data": {},
               "metadata": {"langgraph_node": "formula_agent"}}
        for ch in json.dumps(payload):
            yield {"event": "on_chat_model_stream",
                   "data": {"chunk": _Chunk(ch)},
                   "metadata": {"langgraph_node": "formula_agent"}}
    return _stream


async def _collect(gen):
    return [c async for c in gen]


@pytest.mark.asyncio
async def test_formula_path_always_routes_through_validation_gate():
    # LLM tries to smuggle absurd nutrition and a non-compliant renal formula.
    payload = {
        "type": "formula", "product_name": "Sneaky Shake",
        "ingredients": [
            {"name": "cream heavy", "percentage": 40},
            {"name": "nonfat dry milk", "percentage": 12},
            {"name": "milk whole", "percentage": 34},
            {"name": "sucrose", "percentage": 14},
        ],
        "nutrition_per_100g": {"calories": 1, "protein": 1, "fat": 1, "carbs": 1},
    }
    from langchain_core.messages import HumanMessage
    with patch("main.agent") as m:
        m.astream_events = _formula_stream_factory(payload)
        # Spy on generation, not main: the parse-and-validate adapter moved
        # there so the live eval exercises the same path the API does. The
        # guarantee under test is unchanged — generation.parse_and_validate is
        # the only route from a model proposal to a user-visible formula.
        with patch("generation.validate_candidate",
                   wraps=generation.validate_candidate) as spy:
            chunks = await _collect(
                main._stream_agent([HumanMessage(content="renal formula")],
                                   "sess-gate", active_modules=["renal"]))

    # The gate was invoked exactly once — nothing bypassed it.
    assert spy.call_count == 1

    events = _parse_sse("".join(chunks))
    formula_events = [e for e in events if e.get("type") == "formula"]
    assert len(formula_events) == 1
    f = formula_events[0]["formula"]

    # Numbers are computed, not the smuggled ones.
    assert f["composition"]["nutrients_per_100g"]["energy_kcal"] > 100
    # Renal non-compliance was caught (dairy-heavy).
    assert f["validation"]["passed"] is False
    assert any(v["rule_id"].startswith("renal.")
               for v in f["validation"]["violations"])


@pytest.mark.asyncio
async def test_unresolved_formula_emits_rejection_not_formula():
    payload = {"type": "formula", "product_name": "Ghost",
               "ingredients": [{"name": "unobtainium", "percentage": 100}]}
    from langchain_core.messages import HumanMessage
    with patch("main.agent") as m:
        m.astream_events = _formula_stream_factory(payload)
        chunks = await _collect(
            main._stream_agent([HumanMessage(content="make a formula")],
                               "sess-reject", active_modules=[]))
    events = _parse_sse("".join(chunks))
    assert any(e.get("type") == "rejection" for e in events)
    assert not any(e.get("type") == "formula" for e in events)
