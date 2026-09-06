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
        # /health is a readiness probe now, not a literal {"status": "ok"} echo.
        # Full healthy/degraded coverage lives in tests/test_health.py.
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

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


# ── Routing regressions found by the live eval ────────────────────────────────

class TestEvalFindingRegressions:
    """One test per finding in docs/EVAL_FINDINGS.md.

    The live eval scores these in aggregate; these pin the specific inputs so a
    future pattern edit that reintroduces one fails loudly and by name.
    """

    @pytest.mark.parametrize("message", [
        "Build me a frozen dessert for hemodialysis patients",
        "Create a chocolate ice cream",
        "Develop a novelty frozen dessert for a kids menu",
        "We need a protein-fortified dessert for elderly patients",
        "Create an IDDSI level 4 texture-modified dessert",
        "renal formula",
        "vegan formula please",
    ])
    def test_fe1_product_nouns_route_to_generation(self, message):
        """F-E1: the pattern did not recognise 'dessert' or 'ice cream'."""
        assert detect_intent(message) == "formulate"

    @pytest.mark.parametrize("message", [
        "How much potassium is in coconut cream",
        "make me something",
        "Tell me about renal diet restrictions",
        "What is IDDSI?",
    ])
    def test_fe1_did_not_make_everything_formulate(self, message):
        """Widening the nouns must not swallow ordinary questions."""
        assert detect_intent(message) == "search"

    def test_fe2_an_ingredient_name_does_not_impose_a_clinical_ceiling(self):
        """F-E2: 'nonfat dry milk' activated the low-fat ruleset."""
        from graph import detect_modules

        assert detect_modules("Formulate a renal dessert with nonfat dry milk") == ["renal"]
        assert detect_modules("A dessert using non-fat dry milk") == []

    def test_fe2_the_dietary_sense_still_fires(self):
        from graph import detect_modules

        assert "low_fat" in detect_modules("a non-fat frozen dessert")
        assert "low_fat" in detect_modules("a low-fat dessert")

    @pytest.mark.parametrize("message,module", [
        ("hemodialysis patients", "renal"),
        ("haemodialysis ward", "renal"),
        ("peritoneal dialysis", "renal"),
        ("prediabetic residents", "diabetic"),
        ("a diabetic dessert", "diabetic"),
    ])
    def test_fe3_clinical_stems_are_not_lost_to_word_boundaries(self, message, module):
        """F-E3: the silent one. A missed module means no ruleset runs at all."""
        from graph import detect_modules

        assert module in detect_modules(message), f"{message!r} lost {module}"

    @pytest.mark.parametrize("message,module", [
        ("Create a formula appropriate for a nephrology ward", "renal"),
        ("a dessert for ESRD patients", "renal"),
        ("Design a dessert that will not spike blood glucose", "diabetic"),
        ("something with a low glycaemic index", "diabetic"),
        ("at least 25 g protein per serving", "high_protein"),
    ])
    def test_fe4_clinical_vocabulary_is_recognised(self, message, module):
        """F-E4: unambiguous clinical intent that matched nothing."""
        from graph import detect_modules

        assert module in detect_modules(message), f"{message!r} lost {module}"


class TestRouterAndRagAgent:
    """The router decides whether the clinical rulesets ever get a chance to run.

    It was uncovered until now, which is uncomfortable given the four routing
    defects the eval found (F-E1..F-E4). Those all lived in `detect_intent` and
    `detect_modules`; this covers the layer above them, which chooses whether
    to consult them at all. A brief that reaches `rag_agent` is answered as
    chat and never validated against anything.
    """

    @staticmethod
    def _state(text, **extra):
        from langchain_core.messages import HumanMessage
        return {"messages": [HumanMessage(content=text)], **extra}

    def test_an_explicit_intent_beats_the_text(self):
        """The brief-builder sets intent directly; the regex must not override.

        This is the mitigation that kept F-E1 out of the primary UI path, so it
        deserves a test of its own rather than being assumed.
        """
        import graph
        state = self._state("what is maltodextrin", intent="formulate")
        assert graph.route(state) == "formula_agent"

    def test_a_formulation_brief_without_explicit_intent_routes_to_the_agent(self):
        import graph
        assert graph.route(self._state(
            "Formulate a vegan frozen dessert")) == "formula_agent"

    def test_a_question_routes_to_chat(self):
        import graph
        assert graph.route(self._state(
            "what does locust bean gum do")) == "rag_agent"

    def test_no_human_message_falls_back_to_chat(self):
        """Defensive: an empty turn must not be treated as a formulation."""
        import graph
        assert graph.route({"messages": []}) == "rag_agent"

    def test_clinical_phrasing_reaches_the_formula_agent(self):
        """The F-E3 regression, asserted at the routing layer rather than the
        pattern layer: hemodialysis must not be answered as chat."""
        import graph
        assert graph.route(self._state(
            "Build me a frozen dessert for hemodialysis patients")) == "formula_agent"


class TestRagAgentGrounding:
    def test_the_chat_agent_is_given_usda_context_and_history(self, monkeypatch):
        """The Q&A path must ground answers in the dataset, not free-associate."""
        import graph
        from langchain_core.messages import HumanMessage

        captured = {}

        class _Stub:
            def invoke(self, messages):
                captured["messages"] = messages
                return type("R", (), {"content": "Maltodextrin is a bulking agent."})()

        monkeypatch.setattr(graph, "llm", _Stub())
        monkeypatch.setattr(graph, "search_foods", lambda q: ["MALTODEXTRIN, 380 kcal"])

        out = graph.rag_agent({"messages": [HumanMessage(content="what is maltodextrin")]})

        system_text = " ".join(
            m.content for m in captured["messages"] if hasattr(m, "content"))
        assert "MALTODEXTRIN, 380 kcal" in system_text, "USDA context was not supplied"
        assert "FormulaForge" in system_text, "system prompt missing"
        # Without this the model answers with no idea what was asked; a mutation
        # that dropped conversation history passed until it was added.
        assert "what is maltodextrin" in system_text, "user turn was not forwarded"
        assert out["messages"][-1].content == "Maltodextrin is a bulking agent."

    def test_an_empty_dataset_hit_says_so_rather_than_inventing(self, monkeypatch):
        import graph
        from langchain_core.messages import HumanMessage

        captured = {}

        class _Stub:
            def invoke(self, messages):
                captured["messages"] = messages
                return type("R", (), {"content": "I don't have that."})()

        monkeypatch.setattr(graph, "llm", _Stub())
        monkeypatch.setattr(graph, "search_foods", lambda q: [])

        graph.rag_agent({"messages": [HumanMessage(content="what is unobtainium")]})
        text = " ".join(m.content for m in captured["messages"] if hasattr(m, "content"))
        assert "No matching foods found" in text
