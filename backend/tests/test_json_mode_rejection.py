"""Provider-side JSON validation failures take the repair path (review H10).

Groq answers 400 `json_validate_failed` when JSON-mode output does not parse.
Raised from the formula node, it reached the user as "The formulation agent
encountered an error (BadRequestError)" - found while capturing the README
screenshot - and the one repair the design promises never ran.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

import graph
import main
from tests.test_formula_forge import parse_sse
from tests.test_iteration import _GOOD


def _groq_400(code: str, failed_generation: str = "") -> groq.BadRequestError:
    body = {"error": {"message": "Failed to validate JSON.", "type": "invalid_request_error",
                      "code": code, "failed_generation": failed_generation}}
    response = httpx.Response(400, request=httpx.Request("POST", "http://groq"), json=body)
    return groq.BadRequestError("Error code: 400", response=response, body=body)


class _Raises:
    def __init__(self, exc):
        self.exc = exc

    def invoke(self, messages):
        raise self.exc


def test_json_validate_failed_becomes_an_unparseable_attempt(monkeypatch):
    monkeypatch.setattr(graph, "formula_llm", _Raises(_groq_400("json_validate_failed")))
    assert graph._invoke_formula([]) == ""


def test_the_partial_generation_is_kept(monkeypatch):
    partial = '{"type": "formula", "ingredients": ['
    monkeypatch.setattr(graph, "formula_llm",
                        _Raises(_groq_400("json_validate_failed", partial)))
    assert graph._invoke_formula([]) == partial


def test_other_provider_errors_still_raise(monkeypatch):
    monkeypatch.setattr(graph, "formula_llm", _Raises(_groq_400("model_not_found")))
    with pytest.raises(groq.BadRequestError):
        graph._invoke_formula([])


def test_empty_first_attempt_is_repaired_not_reported_as_an_error():
    """End to end: the node returns "", and the single repair produces the formula."""
    async def _empty_formula_run(*args, **kwargs):
        yield {"event": "on_chain_start", "data": {},
               "metadata": {"langgraph_node": "formula_agent"}}
        yield {"event": "on_chain_end", "name": "formula_agent",
               "data": {"output": {"messages": []}},
               "metadata": {"langgraph_node": "formula_agent"}}

    with patch("main.agent") as agent, \
         patch("main.regenerate_formula", return_value=json.dumps(_GOOD)) as repair:
        agent.astream_events = _empty_formula_run
        res = TestClient(main.app).post("/api/chat", json={"message": "create a vanilla formula"})
    repair.assert_called_once()
    types = [e["type"] for e in parse_sse(res.text)]
    assert "formula" in types and "error" not in types
