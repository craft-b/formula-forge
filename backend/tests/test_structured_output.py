"""A3: structured-output enforcement + one-shot repair reprompt (F2, F13)."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch

import main
from json_utils import extract_json_block
from langchain_core.messages import HumanMessage


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
            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(ch)},
                   "metadata": {"langgraph_node": "formula_agent"}}
    return _stream


async def _collect(gen):
    return [c async for c in gen]


# ── Fence-stripping dedup (F13) ───────────────────────────────────────────────

class TestExtractJsonBlock:
    def test_bare_json_passthrough(self):
        assert extract_json_block('{"a": 1}') == '{"a": 1}'

    def test_strips_json_fence(self):
        assert extract_json_block('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_plain_fence(self):
        assert extract_json_block('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_does_not_mangle_leading_letters(self):
        # The old graph.py lstrip("json") corrupted content; this must not.
        assert extract_json_block('{"name": "jam"}') == '{"name": "jam"}'


# ── Repair reprompt ───────────────────────────────────────────────────────────

_UNRESOLVABLE = {"type": "formula", "product_name": "Ghost",
                 "ingredients": [{"ref": "unobtanium dust", "percentage": 100}]}

_GOOD = {"type": "formula", "product_name": "Fixed Vanilla", "product_format": "standard",
         "ingredients": [{"ref": "milk whole", "percentage": 62},
                         {"ref": "cream heavy", "percentage": 20},
                         {"ref": "sucrose", "percentage": 18}]}


@pytest.mark.asyncio
async def test_rejected_formula_triggers_one_repair_then_succeeds():
    with patch("main.agent") as m:
        m.astream_events = _formula_stream_factory(_UNRESOLVABLE)
        with patch("main.regenerate_formula", return_value=json.dumps(_GOOD)) as regen:
            chunks = await _collect(main._stream_agent(
                [HumanMessage(content="make a vanilla formula")], "s-repair", []))
    assert regen.call_count == 1  # exactly one repair attempt
    events = _parse_sse("".join(chunks))
    formula_events = [e for e in events if e.get("type") == "formula"]
    assert len(formula_events) == 1
    assert formula_events[0]["formula"]["product_name"] == "Fixed Vanilla"


@pytest.mark.asyncio
async def test_repair_not_triggered_for_valid_first_attempt():
    with patch("main.agent") as m:
        m.astream_events = _formula_stream_factory(_GOOD)
        with patch("main.regenerate_formula") as regen:
            chunks = await _collect(main._stream_agent(
                [HumanMessage(content="make a vanilla formula")], "s-norepair", []))
    regen.assert_not_called()
    events = _parse_sse("".join(chunks))
    assert any(e.get("type") == "formula" for e in events)


@pytest.mark.asyncio
async def test_repair_failure_still_emits_rejection():
    with patch("main.agent") as m:
        m.astream_events = _formula_stream_factory(_UNRESOLVABLE)
        with patch("main.regenerate_formula", return_value=json.dumps(_UNRESOLVABLE)):
            chunks = await _collect(main._stream_agent(
                [HumanMessage(content="make a formula")], "s-stillbad", []))
    events = _parse_sse("".join(chunks))
    assert any(e.get("type") == "rejection" for e in events)
