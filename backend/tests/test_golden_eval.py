"""A8: golden-set regression eval for the domain validation + compliance engine.

Runs a curated set of (brief -> formula) cases through validate_candidate with
no LLM, so it is deterministic in CI. Asserts, in aggregate and per case:
  * schema-validity rate (every case parses into a CandidateFormula)
  * mass-balance rate (none rejected for unrepairable sums)
  * compliance accuracy (pass/fail matches the expected outcome, and failures
    fire on the expected constraint module)

This guards the riskiest surface — the domain math and constraint rulesets —
against regression. It does NOT measure LLM generation quality; that is what
eval/live_eval.py does.
"""
from __future__ import annotations

import json
import os

import pytest

from domain import CandidateFormula, validate_candidate

_GOLDEN = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "eval", "golden_formulas.json")

with open(_GOLDEN, encoding="utf-8") as f:
    CASES = json.load(f)["cases"]


def _run(case) -> dict:
    cand = CandidateFormula(
        product_name=case["brief"], product_format=case["format"],
        ingredients=case["ingredients"])
    return {"case": case, "result": validate_candidate(cand, active_modules=case["modules"])}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_case_matches_expectation(case):
    result = _run(case)["result"]
    # Schema-valid and mass-balanced: never a hard rejection in the golden set.
    assert result.type == "formula", f"{case['id']} unexpectedly rejected"

    passed = result.validation.passed
    assert passed == case["expect_pass"], (
        f"{case['id']}: expected pass={case['expect_pass']}, got {passed}")

    if not case["expect_pass"]:
        prefix = case.get("expect_fail_rule_prefix", "")
        error_rules = [v.rule_id for v in result.validation.violations
                       if v.severity == "error"]
        assert any(r.startswith(prefix) for r in error_rules), (
            f"{case['id']}: expected an error rule starting '{prefix}', "
            f"got {error_rules}")


def test_aggregate_rates_meet_thresholds():
    runs = [_run(c) for c in CASES]
    n = len(runs)
    schema_valid = sum(1 for r in runs if r["result"].type == "formula")
    compliance_correct = sum(
        1 for r in runs
        if r["result"].type == "formula"
        and r["result"].validation.passed == r["case"]["expect_pass"])

    # Regression gates — CI fails if these drop.
    assert schema_valid / n == 1.0, "schema-validity regressed below 100%"
    assert compliance_correct / n == 1.0, "compliance accuracy regressed below 100%"
    assert n >= 15, "golden set unexpectedly shrank"
