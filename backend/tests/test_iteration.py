"""A6: parent-anchored iteration + clean history (F7, F9)."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

import main
from graph import detect_iteration


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


async def _collect(gen):
    return [c async for c in gen]


_GOOD = {"type": "formula", "product_name": "Vanilla Base", "product_format": "standard",
         "ingredients": [{"ref": "milk whole", "percentage": 62},
                         {"ref": "cream heavy", "percentage": 20},
                         {"ref": "sucrose", "percentage": 18}]}

_VEGAN_FIX = {"type": "formula", "product_name": "Vanilla Base (vegan)", "product_format": "standard",
              "ingredients": [{"ref": "coconut cream", "percentage": 40},
                              {"ref": "almond milk unsweetened", "percentage": 42},
                              {"ref": "sucrose", "percentage": 17},
                              {"ref": "locust bean gum", "percentage": 1}]}


# ── detect_iteration ──────────────────────────────────────────────────────────

class TestDetectIteration:
    @pytest.mark.parametrize("msg", [
        "now make it dairy-free", "reduce the potassium", "make it creamier",
        "without egg", "lower the fat", "swap the cream", "a vegan version",
    ])
    def test_iteration_phrases(self, msg):
        assert detect_iteration(msg) is True

    @pytest.mark.parametrize("msg", [
        "what is IDDSI?", "how much phosphorus is in whey?",
    ])
    def test_non_iteration_phrases(self, msg):
        assert detect_iteration(msg) is False


# ── Iteration routing carries parent context ──────────────────────────────────

@pytest.mark.asyncio
async def test_iteration_calls_iterate_formula_with_parent():
    parent = "Vanilla Base [standard]: Milk, whole 62%; Cream, heavy 20%; Sucrose 18%"
    with patch("main.iterate_formula", return_value=json.dumps(_VEGAN_FIX)) as it:
        chunks = await _collect(main._stream_agent(
            [HumanMessage(content="now make it dairy-free")],
            "s-iter", active_modules=["vegan"], iteration_parent=parent))
    it.assert_called_once()
    # The parent summary is passed into the iteration prompt.
    assert it.call_args[0][1] == parent
    events = _parse_sse("".join(chunks))
    formula = [e for e in events if e.get("type") == "formula"]
    assert len(formula) == 1
    assert formula[0]["formula"]["product_name"] == "Vanilla Base (vegan)"


@pytest.mark.asyncio
async def test_iteration_path_does_not_call_graph_agent():
    with patch("main.iterate_formula", return_value=json.dumps(_GOOD)), \
         patch("main.agent") as agent_mock:
        await _collect(main._stream_agent(
            [HumanMessage(content="make it sweeter")], "s-noagent",
            active_modules=[], iteration_parent="X [standard]: Sucrose 100%"))
    agent_mock.astream_events.assert_not_called()


# ── History stores a summary, not raw JSON (F9) ───────────────────────────────

def _rag_stream_factory(text: str):
    async def _s(*a, **k):
        yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(text)},
               "metadata": {"langgraph_node": "rag_agent"}}
    return _s


def _formula_stream_factory(payload: dict):
    async def _s(*a, **k):
        yield {"event": "on_chain_start", "data": {},
               "metadata": {"langgraph_node": "formula_agent"}}
        for ch in json.dumps(payload):
            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(ch)},
                   "metadata": {"langgraph_node": "formula_agent"}}
    return _s


@pytest.mark.asyncio
async def test_formula_run_stores_summary_not_raw_json():
    main.conversation_store.pop("s-hist", None)
    main.last_formula_store.pop("s-hist", None)
    with patch("main.agent") as m:
        m.astream_events = _formula_stream_factory(_GOOD)
        await _collect(main._stream_agent(
            [HumanMessage(content="make a vanilla formula")], "s-hist", []))
    stored = main.conversation_store["s-hist"]
    ai = [m for m in stored if isinstance(m, AIMessage)][-1]
    assert ai.content.startswith("[formula]")
    assert "milk whole" not in ai.content  # no raw ingredient JSON leaked
    # And the parent summary is available for a later iteration.
    assert "s-hist" in main.last_formula_store


def test_followup_after_formula_is_routed_as_iteration():
    # End-to-end: first formula, then a modification, via the HTTP endpoint.
    main.conversation_store.clear()
    main.last_formula_store.clear()
    with patch("main.agent") as m:
        m.astream_events = _formula_stream_factory(_GOOD)
        with patch("main.iterate_formula", return_value=json.dumps(_VEGAN_FIX)) as it:
            with TestClient(main.app) as client:
                r1 = client.post("/api/chat", json={"message": "create a vanilla ice cream formula"})
                sid = next(e for e in _parse_sse(r1.text) if e.get("type") == "done")["session_id"]
                r2 = client.post("/api/chat",
                                 json={"message": "now make it vegan", "session_id": sid})
    # The second turn used the iteration path (iterate_formula called), not a
    # RAG answer or a from-scratch generation.
    it.assert_called_once()
    assert any(e.get("type") == "formula" for e in _parse_sse(r2.text))
