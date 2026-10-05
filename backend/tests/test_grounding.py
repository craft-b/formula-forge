"""Q&A grounding: every nutrient figure in an answer is checked against the rows.

The three answers below are the live ones that motivated the check (readiness
review B2): two invented values for things the library does not hold and cited
USDA for them; one quoted the library correctly.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from graph import search_foods
from grounding import has_quantities, ungrounded_quantities
from tests.test_formula_forge import _Chunk, parse_sse

_HEAVY_CREAM_AND_SKIM = search_foods("potassium heavy cream skim milk")


class TestUngroundedQuantities:
    def test_figures_quoted_from_the_rows_are_grounded(self):
        answer = ("- Heavy cream (36 % fat): 97 mg potassium per 100 g\n"
                  "- Skim milk (nonfat): 167 mg potassium per 100 g")
        assert ungrounded_quantities(answer, _HEAVY_CREAM_AND_SKIM) == []

    def test_a_nutrient_the_library_does_not_track_is_ungrounded(self):
        rows = search_foods("whole milk")
        answer = "Vitamin D ~0.1 µg (≈4 IU) and magnesium ~10 mg per 100 g."
        assert ungrounded_quantities(answer, rows) == ["0.1 µg", "4 IU", "10 mg"]

    def test_an_ingredient_not_in_the_library_is_ungrounded(self):
        answer = ("Oat milk has about 30 mg of phosphorus per 100 g, "
                  "roughly 4 % DV, or 72 mg per cup.")
        assert ungrounded_quantities(answer, search_foods("oat milk")) == [
            "30 mg", "72 mg", "4 % DV"]

    def test_rounding_in_the_rows_is_not_mistaken_for_invention(self):
        rows = ["Milk, whole, 3.25% fat: 61 kcal, 3.15g protein (per 100 g)"]
        assert ungrounded_quantities("about 3.2 g protein and 61 kcal", rows) == []

    def test_a_matching_number_in_another_unit_does_not_ground(self):
        """10 mg of sodium in a row does not vouch for 10 g of anything."""
        rows = ["Guar gum: 155 kcal, 5.0g protein, P 0mg, K 100mg, Na 10mg (per 100 g)"]
        assert ungrounded_quantities("it has 10 g of fibre", rows) == ["10 g"]

    def test_daily_value_claims_are_always_ungrounded(self):
        rows = ["Milk, whole: P 84mg (per 100 g)"]
        assert ungrounded_quantities("84 mg, which is 12% of the daily value", rows) == [
            "12% of the daily value"]

    def test_prose_without_figures(self):
        assert not has_quantities("Locust bean gum and guar are both good choices.")
        assert has_quantities("about 97 mg")


def test_chat_emits_grounding_after_a_rag_answer():
    """The client is told which figures the library did not supply."""
    from main import app

    async def _rag_sse(*args, **kwargs):
        for token in ["Oat milk has ", "about 30 mg ", "phosphorus per 100 g."]:
            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(token)},
                   "metadata": {"langgraph_node": "rag_agent"}}
        yield {"event": "on_chain_end", "name": "rag_agent",
               "data": {"output": {"messages": [], "context": search_foods("oat milk")}},
               "metadata": {"langgraph_node": "rag_agent"}}

    with patch("main.agent") as agent:
        agent.astream_events = _rag_sse
        res = TestClient(app).post("/api/chat", json={"message": "phosphorus in oat milk?"})
    events = parse_sse(res.text)
    grounding = [e for e in events if e["type"] == "grounding"]
    assert grounding == [{"type": "grounding", "has_quantities": True,
                          "ungrounded": ["30 mg"]}]
    assert events[-1]["type"] == "done"


def test_formula_runs_do_not_emit_grounding():
    """Formula numbers are recomputed by the domain; there is nothing to ground."""
    from main import app
    from tests.test_formula_forge import _formula_sse

    with patch("main.agent") as agent:
        agent.astream_events = _formula_sse
        res = TestClient(app).post("/api/chat", json={"message": "create a renal formula"})
    assert not [e for e in parse_sse(res.text) if e["type"] == "grounding"]
