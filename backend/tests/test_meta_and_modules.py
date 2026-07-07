"""Tests for /api/meta and explicit module selection in ChatRequest."""
from __future__ import annotations

import json

from unittest.mock import patch
from fastapi.testclient import TestClient

import main


class _Chunk:
    def __init__(self, c): self.content = c


def _formula_stream(payload: dict):
    async def _s(*a, **k):
        yield {"event": "on_chain_start", "data": {},
               "metadata": {"langgraph_node": "formula_agent"}}
        for ch in json.dumps(payload):
            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(ch)},
                   "metadata": {"langgraph_node": "formula_agent"}}
    return _s


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


class TestMeta:
    def test_meta_shape(self):
        with TestClient(main.app) as client:
            r = client.get("/api/meta")
        assert r.status_code == 200
        body = r.json()
        assert body["ingredient_count"] >= 30
        assert body["dataset_version"]
        ids = {m["id"] for m in body["modules"]}
        assert {"renal", "diabetic", "vegan"} <= ids
        stub = next(m for m in body["modules"] if m["id"] == "dysphagia_iddsi")
        assert stub["stub"] is True


class TestExplicitModules:
    # Premium (25% overrun → ~139 g mix/serving): this dairy mix computes to
    # ~300 mg K per serving, over the renal 200 mg limit. At "standard" 100%
    # overrun the same mix would PASS (air halves the serving mass) — per-serving
    # compliance is overrun-dependent by design.
    _DAIRY = {"type": "formula", "product_name": "Dairy Vanilla",
              "product_format": "premium",
              "ingredients": [{"ref": "milk whole", "percentage": 58},
                              {"ref": "cream heavy", "percentage": 22},
                              {"ref": "sucrose", "percentage": 14},
                              {"ref": "nonfat dry milk", "percentage": 6}]}

    def test_brief_builder_modules_are_enforced(self):
        # Message contains NO renal keywords; module comes from the request body.
        with patch("main.agent") as m:
            m.astream_events = _formula_stream(self._DAIRY)
            with patch("main.regenerate_formula",
                       return_value=json.dumps(self._DAIRY)):
                with TestClient(main.app) as client:
                    r = client.post("/api/chat", json={
                        "message": "create a vanilla ice cream formula",
                        "modules": ["renal"],
                    })
        events = _parse_sse(r.text)
        formula = next(e for e in events if e.get("type") == "formula")["formula"]
        assert "renal" in formula["validation"]["active_modules"]
        assert formula["validation"]["passed"] is False  # dairy fails renal K/P

    def test_unknown_module_ids_ignored(self):
        with patch("main.agent") as m:
            m.astream_events = _formula_stream(self._DAIRY)
            with TestClient(main.app) as client:
                r = client.post("/api/chat", json={
                    "message": "create a vanilla ice cream formula",
                    "modules": ["nonexistent_module"],
                })
        events = _parse_sse(r.text)
        formula = next(e for e in events if e.get("type") == "formula")["formula"]
        assert formula["validation"]["active_modules"] == []
