"""
Tests for FormulaForge backend.

Agent LLM calls are mocked throughout — these tests verify intent routing,
food search scoring, formula JSON parsing, and API contract without hitting
the Groq API. Run from backend/: pytest tests/ -v
"""
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from graph import detect_intent, search_foods
from main import app


# ── Helpers ───────────────────────────────────────────────────────────────────

class _Chunk:
    """Minimal stand-in for a LangChain AIMessageChunk."""
    def __init__(self, content: str):
        self.content = content


def parse_sse(text: str) -> list[dict]:
    """Parse an SSE response body into a list of event dicts."""
    events = []
    for part in text.split("\n\n"):
        part = part.strip()
        if not part.startswith("data: "):
            continue
        payload = part[6:]
        if payload == "[DONE]":
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return events


# ── Shared test data ──────────────────────────────────────────────────────────

VALID_FORMULA = {
    "type": "formula",
    "product_name": "Test Renal Shake",
    "description": "Low-phosphorus protein supplement for CKD patients",
    "ingredients": [
        {"name": "Whey protein isolate", "percentage": 100.0, "notes": "Low phosphorus"}
    ],
    "nutrition_per_100g": {
        "calories": 400, "protein": 30.0, "fat": 5.0, "carbs": 40.0
    },
    "formulation_notes": "Verify phosphorus content against KDOQI guidelines.",
}


# ── Fixtures ──────────────────────────────────────────────────────────────────

async def _default_sse(*args, **kwargs):
    """Default mock: yields a single RAG token."""
    yield {
        "event": "on_chat_model_stream",
        "data": {"chunk": _Chunk("Mocked LLM response")},
        "metadata": {"langgraph_node": "rag_agent"},
    }


async def _formula_sse(*args, **kwargs):
    """Mock that simulates a formula_agent run yielding JSON token-by-token."""
    yield {
        "event": "on_chain_start",
        "data": {},
        "metadata": {"langgraph_node": "formula_agent"},
    }
    for char in json.dumps(VALID_FORMULA):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": _Chunk(char)},
            "metadata": {"langgraph_node": "formula_agent"},
        }


async def _error_sse(*args, **kwargs):
    """Mock that raises immediately, simulating a Groq API failure."""
    raise RuntimeError("Groq timeout")
    yield  # makes this an async generator


@pytest.fixture
def mock_agent():
    with patch("main.agent") as m:
        m.astream_events = _default_sse
        yield m


@pytest.fixture
def client(mock_agent):
    with TestClient(app) as c:
        yield c


# ── Intent detection ──────────────────────────────────────────────────────────

class TestDetectIntent:

    @pytest.mark.parametrize("message", [
        "Please formulate a high-protein renal shake",
        "I'm formulating a new oncology product",
        "Create a formula for dysphagia-safe pudding",
        "Build me an enteral nutrition formula",
        "Give me a recipe for a tube feed supplement",
        "I need a formula for CKD patients",
        "Let's develop a new formulation for post-surgical recovery",
        "Generate a formula for a low-phosphorus meal replacement",
    ])
    def test_formulate_intent_detected(self, message):
        assert detect_intent(message) == "formulate"

    @pytest.mark.parametrize("message", [
        "What protein sources work for dysphagia?",
        "How much phosphorus is in whey protein isolate?",
        "Tell me about renal diet restrictions",
        "What is IDDSI?",
        "hello",
        "List ingredients high in potassium",
    ])
    def test_search_intent_detected(self, message):
        assert detect_intent(message) == "search"


# ── Food search ───────────────────────────────────────────────────────────────

class TestSearchFoods:

    def test_returns_list_of_strings(self):
        results = search_foods("whey protein")
        assert isinstance(results, list)
        assert all(isinstance(r, str) for r in results)

    def test_respects_n_limit(self):
        assert len(search_foods("protein", n=3)) <= 3

    def test_no_match_returns_empty_list(self):
        assert search_foods("xyzzy nonsense token qqqq", n=5) == []

    def test_short_words_are_ignored(self):
        # "a", "of", "in" are under 3 chars and should not affect scoring
        assert search_foods("a protein of in") == search_foods("protein")


# ── Formula JSON parsing ──────────────────────────────────────────────────────

class TestFormulaJsonParsing:

    def test_valid_formula_json_parses_correctly(self):
        parsed = json.loads(json.dumps(VALID_FORMULA))
        assert parsed["type"] == "formula"
        assert parsed["product_name"] == "Test Renal Shake"

    def test_plain_text_raises_json_decode_error(self):
        with pytest.raises(json.JSONDecodeError):
            json.loads("This is a plain text answer about nutrition.")

    def test_json_without_formula_type_not_treated_as_formula(self):
        parsed = json.loads(json.dumps({"data": "something", "value": 42}))
        assert parsed.get("type") != "formula"

    def test_formula_has_all_required_fields(self):
        for field in ("product_name", "ingredients", "nutrition_per_100g", "formulation_notes"):
            assert field in VALID_FORMULA


# ── API endpoints ─────────────────────────────────────────────────────────────

class TestApiEndpoints:

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_chat_valid_message_returns_200(self, client):
        response = client.post("/api/chat", json={"message": "What is whey protein?"})
        assert response.status_code == 200
        events = parse_sse(response.text)
        done = [e for e in events if e.get("type") == "done"]
        assert len(done) == 1

    def test_chat_empty_message_returns_422(self, client):
        assert client.post("/api/chat", json={"message": ""}).status_code == 422

    def test_chat_message_too_long_returns_422(self, client):
        assert client.post("/api/chat", json={"message": "x" * 2001}).status_code == 422

    def test_chat_generates_uuid_session_id(self, client):
        response = client.post("/api/chat", json={"message": "Tell me about protein"})
        events = parse_sse(response.text)
        done = next(e for e in events if e.get("type") == "done")
        assert len(done["session_id"]) == 36  # UUID4 hyphenated: 8-4-4-4-12

    def test_chat_preserves_provided_session_id(self, client):
        sid = "user-session-abc-123"
        response = client.post("/api/chat", json={"message": "Hello", "session_id": sid})
        events = parse_sse(response.text)
        done = next(e for e in events if e.get("type") == "done")
        assert done["session_id"] == sid

    def test_chat_rag_response_sends_token_events(self, client):
        response = client.post("/api/chat", json={"message": "What is whey protein?"})
        events = parse_sse(response.text)
        tokens = [e for e in events if e.get("type") == "token"]
        assert len(tokens) > 0
        assert tokens[0]["content"] == "Mocked LLM response"

    def test_chat_formula_response_sends_formula_event(self, client, mock_agent):
        mock_agent.astream_events = _formula_sse
        response = client.post(
            "/api/chat",
            json={"message": "Create a formula for a renal shake"},
        )
        assert response.status_code == 200
        events = parse_sse(response.text)
        formula_events = [e for e in events if e.get("type") == "formula"]
        assert len(formula_events) == 1
        assert formula_events[0]["formula"]["product_name"] == "Test Renal Shake"

    def test_chat_agent_error_sends_error_event(self, client, mock_agent):
        mock_agent.astream_events = _error_sse
        response = client.post("/api/chat", json={"message": "Create a formula"})
        assert response.status_code == 200  # HTTP 200 — error travels inside the stream
        events = parse_sse(response.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
