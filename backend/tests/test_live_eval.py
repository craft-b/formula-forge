"""Tests for the live-eval harness itself.

A harness that gates CI has to be trustworthy before its numbers mean anything:
a broken interval or an over-eager gate would either block every merge or wave
regressions through. Everything here is deterministic and makes no API call —
generation is exercised against a stub model.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from eval import live_eval


# ── the statistics ────────────────────────────────────────────────────────────

class TestWilson:
    def test_empty_sample_is_not_a_division_error(self):
        assert live_eval.wilson(0, 0) == (0.0, 0.0, 0.0)

    def test_perfect_score_does_not_get_a_zero_width_interval(self):
        """The reason for Wilson over the normal approximation.

        10/10 is not evidence that the true rate is exactly 1.0, and an
        interval that says so would make the gate fire on the first unlucky
        run.
        """
        point, low, high = live_eval.wilson(10, 10)
        assert point == 1.0
        assert high == 1.0
        assert 0.70 < low < 0.75  # known Wilson bound for 10/10 at 95%

    def test_interval_never_leaves_zero_to_one(self):
        for successes, n in [(0, 5), (1, 5), (5, 5), (1, 100), (99, 100)]:
            _, low, high = live_eval.wilson(successes, n)
            assert 0.0 <= low <= high <= 1.0

    def test_interval_narrows_as_the_sample_grows(self):
        _, low_small, high_small = live_eval.wilson(8, 10)
        _, low_big, high_big = live_eval.wilson(80, 100)
        assert (high_big - low_big) < (high_small - low_small)

    def test_point_estimate_is_the_plain_proportion(self):
        assert live_eval.wilson(3, 4)[0] == pytest.approx(0.75)


class TestRate:
    def test_reports_point_and_bounds(self):
        rate = live_eval.Rate("x", 9, 10)
        payload = rate.as_dict()
        assert payload["point"] == pytest.approx(0.9)
        assert payload["ci_low"] < 0.9 < payload["ci_high"]
        assert payload["n"] == 10


# ── the gate ──────────────────────────────────────────────────────────────────

class TestGate:
    """The gate must catch real regressions without firing on sampling noise."""

    @staticmethod
    def _baseline(name: str, successes: int, n: int) -> dict:
        point, low, _ = live_eval.wilson(successes, n)
        return {"rates": {name: {"point": point, "ci_low": low}}}

    def test_a_small_drop_within_sampling_error_does_not_fail(self):
        # 45/46 against a 100% baseline: worse, but one case is noise here.
        rates = [live_eval.Rate("module_detection", 45, 46)]
        assert live_eval.check_gate(
            rates, self._baseline("module_detection", 46, 46)) == []

    def test_a_collapse_fails(self):
        rates = [live_eval.Rate("module_detection", 20, 46)]
        failures = live_eval.check_gate(rates, self._baseline("module_detection", 44, 46))
        assert len(failures) == 1
        assert "module_detection" in failures[0]

    def test_an_improvement_never_fails(self):
        rates = [live_eval.Rate("gate_pass_first_try", 46, 46)]
        assert live_eval.check_gate(
            rates, self._baseline("gate_pass_first_try", 37, 46)) == []

    def test_a_metric_absent_from_the_baseline_is_skipped(self):
        """A newly added metric must not fail the build before it has a baseline."""
        rates = [live_eval.Rate("brand_new_metric", 0, 10)]
        assert live_eval.check_gate(rates, self._baseline("something_else", 10, 10)) == []

    def test_a_tiny_sample_is_not_gated_on(self):
        """Five observations cannot distinguish a regression from luck."""
        rates = [live_eval.Rate("repair_recovery", 0, 5)]
        assert live_eval.check_gate(rates, self._baseline("repair_recovery", 10, 10)) == []


# ── the dataset ───────────────────────────────────────────────────────────────

class TestBriefs:
    """Guards the labelled set: a malformed case would silently skew every rate."""

    CASES = live_eval.load_cases()

    def test_the_set_has_not_shrunk(self):
        assert len(self.CASES) >= 40

    def test_ids_are_unique(self):
        ids = [c["id"] for c in self.CASES]
        assert len(ids) == len(set(ids))

    def test_every_case_carries_the_required_labels(self):
        required = {"id", "brief", "expect_modules", "expect_intent",
                    "expect_gate_pass", "category"}
        for case in self.CASES:
            assert required <= set(case), f"{case.get('id')} is missing labels"

    def test_expected_modules_exist(self):
        from domain import available_modules

        known = set(available_modules())
        for case in self.CASES:
            unknown = set(case["expect_modules"]) - known
            assert not unknown, f"{case['id']} names unknown modules {unknown}"

    def test_intent_labels_are_valid(self):
        for case in self.CASES:
            assert case["expect_intent"] in {"formulate", "search"}, case["id"]

    def test_non_formulation_cases_expect_no_gate_result(self):
        """`search` briefs never reach generation, so a gate expectation there
        would be scored against something that never runs."""
        for case in self.CASES:
            if case["expect_intent"] == "search":
                assert case["expect_gate_pass"] is None, case["id"]

    def test_adversarial_and_constraint_coverage(self):
        categories = {c["category"] for c in self.CASES}
        for needed in ("single_module", "multi_module", "contradiction",
                       "off_domain", "phrasing_gap"):
            assert needed in categories, f"no {needed} cases"


# ── routing and generation ────────────────────────────────────────────────────

class TestScoreRouting:
    def test_scores_a_hit_and_a_miss(self):
        cases = [
            {"id": "hit", "brief": "Formulate a vegan frozen dessert",
             "expect_modules": ["vegan"], "expect_intent": "formulate",
             "expect_gate_pass": True, "category": "single_module"},
            {"id": "miss", "brief": "Formulate a vegan frozen dessert",
             "expect_modules": ["renal"], "expect_intent": "formulate",
             "expect_gate_pass": True, "category": "single_module"},
        ]
        results = live_eval.score_routing(cases)
        assert results[0].modules_ok is True
        assert results[1].modules_ok is False
        assert results[1].modules_detected == ["vegan"]


_GOOD_FORMULA = json.dumps({
    "type": "formula", "product_name": "Test Vegan",
    "product_format": "standard",
    "ingredients": [
        {"ref": "coconut cream", "percentage": 42},
        {"ref": "almond milk unsweetened", "percentage": 39},
        {"ref": "sucrose", "percentage": 15},
        {"ref": "maltodextrin de10", "percentage": 3},
        {"ref": "locust bean gum", "percentage": 1},
    ],
    "formulation_notes": "Freeze at standard overrun.",
})

_PHANTOM_FORMULA = json.dumps({
    "type": "formula", "product_name": "Ghost",
    "product_format": "standard",
    "ingredients": [{"ref": "unobtainium", "percentage": 100}],
    "formulation_notes": "",
})


class TestScoreGeneration:
    """Generation scoring against a stub model — no API key, no cost."""

    CASE = {"id": "vegan_plain", "brief": "Formulate a vegan frozen dessert",
            "expect_modules": ["vegan"], "expect_intent": "formulate",
            "expect_gate_pass": True, "category": "single_module"}

    def _run(self, raw: str):
        results = live_eval.score_routing([self.CASE])
        with patch("graph._invoke_formula", return_value=raw):
            live_eval.score_generation([self.CASE], results, repair=False)
        return results[0]

    def test_a_compliant_formula_scores_clean(self):
        result = self._run(_GOOD_FORMULA)
        assert result.generated is True
        assert result.resolved is True
        assert result.gate_passed_first is True
        assert result.violations == []

    def test_a_phantom_ingredient_is_a_grounding_failure(self):
        result = self._run(_PHANTOM_FORMULA)
        assert result.generated is True
        assert result.resolved is False
        assert result.gate_passed_first is False

    def test_unparseable_output_is_recorded_not_raised(self):
        result = self._run("I'm afraid I can't do that.")
        assert result.generated is False
        assert result.error == "unparseable"

    def test_a_model_exception_does_not_abort_the_run(self):
        """One failing case must not cost the other forty-five."""
        results = live_eval.score_routing([self.CASE])
        with patch("graph._invoke_formula", side_effect=RuntimeError("rate limited")):
            live_eval.score_generation([self.CASE], results, repair=False)
        assert "RuntimeError" in results[0].error

    def test_search_only_briefs_are_never_generated(self):
        case = {"id": "q", "brief": "How much potassium is in coconut cream",
                "expect_modules": [], "expect_intent": "search",
                "expect_gate_pass": None, "category": "off_domain"}
        results = live_eval.score_routing([case])
        with patch("graph._invoke_formula", side_effect=AssertionError("must not generate")):
            live_eval.score_generation([case], results, repair=False)
        assert results[0].generated is None


class TestSummarise:
    def test_offline_reports_routing_only(self):
        cases = live_eval.load_cases()[:5]
        rates = live_eval.summarise(cases, live_eval.score_routing(cases), live=False)
        names = {r.name for r in rates}
        assert "intent_routing" in names
        assert "gate_pass_first_try" not in names

    def test_render_produces_a_table(self):
        cases = live_eval.load_cases()[:5]
        results = live_eval.score_routing(cases)
        report = live_eval.render(
            live_eval.summarise(cases, results, live=False), results, live=False)
        assert "| Metric |" in report
        assert "intent_routing" in report


class TestRepairPathEndToEnd:
    """The repair branch, exercised for real against a stubbed provider.

    Every other test here patches `_invoke_formula`, which skips the whole
    repair chain — and the nightly workflow runs with repair ON. Patching at the
    LLM object instead lets the real code run: build_formula_messages →
    formula_llm.invoke → extract_json_block → parse_and_validate →
    _repair_feedback → regenerate_formula → invoke again. A signature or
    attribute error in there would otherwise first appear at 07:00 UTC in CI
    with nobody watching.
    """

    CASE = {"id": "renal_repair", "brief": "Formulate a renal-safe dessert",
            "expect_modules": ["renal"], "expect_intent": "formulate",
            "expect_gate_pass": True, "category": "single_module"}

    # Dairy-heavy: fails the renal ruleset on potassium/phosphorus.
    FAILING = json.dumps({
        "type": "formula", "product_name": "Rich Dairy",
        "product_format": "premium",
        "ingredients": [
            {"ref": "cream heavy", "percentage": 30},
            {"ref": "nonfat dry milk", "percentage": 12},
            {"ref": "sucrose", "percentage": 14},
            {"ref": "milk whole", "percentage": 43.4},
            {"ref": "locust bean gum", "percentage": 0.6},
        ],
        "formulation_notes": "",
    })

    class _Reply:
        def __init__(self, content):
            self.content = content

    def _fake_llm(self, replies: list[str], seen: list):
        class _LLM:
            def invoke(_self, messages):
                seen.append(messages)
                return TestRepairPathEndToEnd._Reply(replies[min(len(seen) - 1,
                                                                len(replies) - 1)])
        return _LLM()

    def test_a_failed_formula_is_repaired_and_scored(self):
        seen: list = []
        results = live_eval.score_routing([self.CASE])
        with patch("graph.formula_llm", self._fake_llm([self.FAILING, _GOOD_FORMULA], seen)):
            live_eval.score_generation([self.CASE], results, repair=True)

        result = results[0]
        assert result.gate_passed_first is False, "the dairy formula must fail renal"
        assert result.gate_passed_after_repair is True, "the retry should clear it"
        assert len(seen) == 2, "exactly one repair call, as in production"

    def test_the_repair_prompt_carries_the_violation_feedback(self):
        """A retry that is not told what broke is just a second guess."""
        seen: list = []
        results = live_eval.score_routing([self.CASE])
        with patch("graph.formula_llm", self._fake_llm([self.FAILING, _GOOD_FORMULA], seen)):
            live_eval.score_generation([self.CASE], results, repair=True)

        retry_prompt = "".join(m.content for m in seen[1])
        assert "REJECTED" in retry_prompt
        assert "renal." in retry_prompt, "the failing rule id should reach the model"

    def test_a_repair_that_also_fails_is_recorded_not_raised(self):
        seen: list = []
        results = live_eval.score_routing([self.CASE])
        with patch("graph.formula_llm", self._fake_llm([self.FAILING, self.FAILING], seen)):
            live_eval.score_generation([self.CASE], results, repair=True)
        assert results[0].gate_passed_after_repair is False

    def test_a_passing_first_attempt_costs_no_repair_call(self):
        """Cost control: repair must not fire when nothing is wrong."""
        seen: list = []
        case = dict(self.CASE, id="vegan_ok", brief="Formulate a vegan frozen dessert",
                    expect_modules=["vegan"])
        results = live_eval.score_routing([case])
        with patch("graph.formula_llm", self._fake_llm([_GOOD_FORMULA], seen)):
            live_eval.score_generation([case], results, repair=True)
        assert results[0].gate_passed_first is True
        assert len(seen) == 1, "no repair call should have been made"
