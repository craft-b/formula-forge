"""Domain-layer tests (A2): composition math, validation gate, constraint modules.

The mass-balance and nutrient math carry property-based tests (hypothesis) per
the build invariants. Everything here exercises the pure domain in isolation —
no FastAPI, no LangGraph, no LLM.
"""
from __future__ import annotations


import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from domain import (
    CandidateFormula,
    compute_composition,
    mass_balance_error,
    mass_balance_ok,
    validate_candidate,
)
from domain.composition import serving_grams
from domain.models import NutrientVector
from domain.repository import get_repository

REPO = get_repository()
_IDS = [i.id for i in REPO.ingredients]


def _specs(*ids):
    return [REPO.get(i) for i in ids]


# ── Property-based: mass balance ──────────────────────────────────────────────

@given(st.lists(st.floats(min_value=0.1, max_value=100), min_size=1, max_size=12))
def test_mass_balance_error_is_abs_distance_from_100(pcts):
    assert mass_balance_error(pcts) == pytest.approx(abs(sum(pcts) - 100.0))


@given(st.lists(st.floats(min_value=0.1, max_value=50), min_size=2, max_size=8))
def test_normalized_percentages_pass_mass_balance(pcts):
    total = sum(pcts)
    normed = [p * 100.0 / total for p in pcts]
    assert mass_balance_ok(normed)


# ── Property-based: nutrient math is linear and non-negative ──────────────────

@given(
    a=st.floats(min_value=1, max_value=99),
    ing_pair=st.tuples(
        st.sampled_from(_IDS[:8]), st.sampled_from(_IDS[8:16]),
    ),
)
@settings(max_examples=40)
def test_composition_nonnegative_and_bounded(a, ing_pair):
    id1, id2 = ing_pair
    if id1 == id2:
        return
    b = 100 - a
    specs = _specs(id1, id2)
    comp = compute_composition([(specs[0], a), (specs[1], b)])
    v = comp.nutrients_per_100g
    for field in NutrientVector.model_fields:
        val = getattr(v, field)
        assert val >= -1e-6, f"{field} negative"
    # Total solids and water are complementary and within [0, 100].
    assert -1e-6 <= comp.total_solids_pct <= 100.0 + 1e-6
    assert 0.0 <= v.water_g <= 100.0 + 1e-6


@given(scale=st.floats(min_value=0.1, max_value=1.0))
@settings(max_examples=25)
def test_nutrient_contribution_scales_linearly(scale):
    # Doubling a single ingredient's share doubles its per-100g contribution
    # (checked via a one-ingredient mix at pct and 2*pct, normalised out).
    spec = REPO.get("sucrose")
    pct = 40.0 * scale
    c1 = compute_composition([(spec, pct)])
    c2 = compute_composition([(spec, 2 * pct)])
    # abs tolerance covers the 3-dp rounding in the weighted sum.
    assert c2.nutrients_per_100g.carbs_g == pytest.approx(
        2 * c1.nutrients_per_100g.carbs_g, abs=0.01)


# ── Per-serving / overrun math ────────────────────────────────────────────────

def test_higher_overrun_gives_lighter_serving():
    assert serving_grams(100.0) < serving_grams(20.0)


def test_per_serving_scales_from_per_100g():
    comp = compute_composition([(REPO.get("milk_whole"), 100.0)], overrun_pct=100.0)
    ratio = comp.serving_g / 100.0
    assert comp.nutrients_per_serving.energy_kcal == pytest.approx(
        comp.nutrients_per_100g.energy_kcal * ratio, rel=1e-6)


# ── PAC / POD sanity ──────────────────────────────────────────────────────────

def test_erythritol_depresses_freezing_more_than_sucrose():
    # Equal inclusion; erythritol PAC factor (280) >> sucrose (100).
    suc = compute_composition([(REPO.get("sucrose"), 15.0), (REPO.get("milk_skim"), 85.0)])
    ery = compute_composition([(REPO.get("erythritol"), 15.0), (REPO.get("milk_skim"), 85.0)])
    assert ery.pac_total > suc.pac_total


def test_fructose_sweeter_than_sucrose_same_mass():
    suc = compute_composition([(REPO.get("sucrose"), 15.0), (REPO.get("milk_skim"), 85.0)])
    fru = compute_composition([(REPO.get("fructose"), 15.0), (REPO.get("milk_skim"), 85.0)])
    assert fru.pod_total > suc.pod_total


# ── Validation gate ───────────────────────────────────────────────────────────

def _renal_ok_formula():
    return CandidateFormula(
        product_name="Renal Vanilla", product_format="premium",
        ingredients=[
            {"ref": "whey protein isolate", "percentage": 4},
            {"ref": "coconut cream", "percentage": 22},
            {"ref": "maltodextrin de10", "percentage": 8},
            {"ref": "sucrose", "percentage": 12},
            {"ref": "dextrose", "percentage": 4},
            {"ref": "almond milk unsweetened", "percentage": 47.5},
            {"ref": "locust bean gum", "percentage": 0.3},
            {"ref": "vanilla extract", "percentage": 2.2},
        ],
    )


def test_compliant_renal_formula_passes():
    res = validate_candidate(_renal_ok_formula(), active_modules=["renal"])
    assert res.type == "formula"
    assert res.validation.passed
    # Every displayed number is computed, not supplied.
    assert res.composition.nutrients_per_serving.phosphorus_mg <= 120.0


def test_dairy_heavy_formula_fails_renal():
    cand = CandidateFormula(
        product_name="Dairy Premium", product_format="premium",
        ingredients=[
            {"ref": "cream heavy", "percentage": 30},
            {"ref": "nonfat dry milk", "percentage": 12},
            {"ref": "sucrose", "percentage": 14},
            {"ref": "milk whole", "percentage": 43.4},
            {"ref": "locust bean gum", "percentage": 0.6},
        ],
    )
    res = validate_candidate(cand, active_modules=["renal"])
    assert res.type == "formula"
    assert res.validation.passed is False
    error_rules = {v.rule_id for v in res.validation.violations if v.severity == "error"}
    assert "renal.potassium" in error_rules or "renal.phosphorus" in error_rules


def test_vegan_rejects_dairy_and_egg():
    cand = CandidateFormula(
        product_name="Not Vegan", product_format="standard",
        ingredients=[{"ref": "cream heavy", "percentage": 40},
                     {"ref": "sucrose", "percentage": 14},
                     {"ref": "milk whole", "percentage": 46}],
    )
    res = validate_candidate(cand, active_modules=["vegan"])
    assert res.validation.passed is False
    assert any(v.rule_id.startswith("vegan.") for v in res.validation.violations)


def test_unresolved_ingredient_is_rejected_not_guessed():
    cand = CandidateFormula(
        product_name="Mystery",
        ingredients=[{"ref": "unobtainium powder", "percentage": 100}])
    res = validate_candidate(cand, active_modules=[])
    assert res.type == "rejection"
    assert "unobtainium powder" in res.unresolved_ingredients


def test_mass_balance_is_repaired():
    cand = CandidateFormula(
        product_name="Off Sum", product_format="standard",
        ingredients=[{"ref": "milk whole", "percentage": 60},
                     {"ref": "cream heavy", "percentage": 20},
                     {"ref": "sucrose", "percentage": 18}])  # sums to 98
    res = validate_candidate(cand, active_modules=[])
    assert res.type == "formula"
    assert res.validation.repaired is True
    assert sum(l.percentage for l in res.ingredients) == pytest.approx(100.0, abs=0.01)


def test_wildly_off_mass_balance_is_rejected():
    cand = CandidateFormula(
        product_name="Broken", product_format="standard",
        ingredients=[{"ref": "milk whole", "percentage": 20},
                     {"ref": "sucrose", "percentage": 10}])  # sums to 30
    res = validate_candidate(cand, active_modules=[])
    assert res.type == "rejection"


def test_dysphagia_stub_advises_but_never_fails():
    cand = CandidateFormula(
        product_name="Std", product_format="standard",
        ingredients=[{"ref": "milk whole", "percentage": 62},
                     {"ref": "cream heavy", "percentage": 20},
                     {"ref": "sucrose", "percentage": 18}])
    res = validate_candidate(cand, active_modules=["dysphagia_iddsi"])
    assert res.validation.passed is True
    assert any(v.rule_id == "dysphagia_iddsi.stub" and v.severity == "warn"
               for v in res.validation.violations)


def test_llm_supplied_nutrition_cannot_enter():
    # CandidateFormula has no nutrition fields; extra keys are ignored by pydantic.
    cand = CandidateFormula.model_validate({
        "product_name": "Sneaky", "product_format": "standard",
        "ingredients": [{"ref": "milk whole", "percentage": 100}],
        "nutrition_per_100g": {"calories": 99999, "protein": 99999},
    })
    assert not hasattr(cand, "nutrition_per_100g")
    res = validate_candidate(cand, active_modules=[])
    # Energy is computed from milk, nowhere near the injected 99999.
    assert res.composition.nutrients_per_100g.energy_kcal < 200


def test_llm_supplied_overrun_cannot_enter():
    """Overrun divides every per-serving value, so the model must not set it.

    serving_g = RACC / (1 + overrun) x density, and per-serving is the basis
    every clinical limit is checked against. A model that could raise overrun
    could shrink the serving and make a non-compliant formula pass.
    """
    payload = {
        "product_name": "Sneaky overrun", "product_format": "premium",
        "ingredients": [{"ref": "milk whole", "percentage": 100}],
        "overrun_pct": 300.0,
    }
    cand = CandidateFormula.model_validate(payload)
    assert not hasattr(cand, "overrun_pct")

    res = validate_candidate(cand, active_modules=[])
    # premium is 25% overrun, not the 300% the model asked for.
    assert res.composition.overrun_pct == 25.0


def test_overrun_authority_belongs_to_the_caller():
    """The caller may still set overrun on the user's behalf."""
    cand = CandidateFormula.model_validate({
        "product_name": "Explicit", "product_format": "premium",
        "ingredients": [{"ref": "milk whole", "percentage": 100}]})

    from_format = validate_candidate(cand, active_modules=[])
    from_caller = validate_candidate(cand, active_modules=[], overrun_pct=100.0)

    assert from_format.composition.overrun_pct == 25.0
    assert from_caller.composition.overrun_pct == 100.0
    # Higher overrun means less mix per serving.
    assert from_caller.composition.serving_g < from_format.composition.serving_g


def test_model_cannot_move_a_clinical_verdict_via_overrun():
    """The whole point: a renal verdict must not depend on model-supplied text."""
    lines = [{"ref": "milk whole", "percentage": 58},
             {"ref": "cream heavy", "percentage": 22},
             {"ref": "sucrose", "percentage": 14},
             {"ref": "nonfat dry milk", "percentage": 6}]

    honest = CandidateFormula.model_validate({
        "product_name": "Renal", "product_format": "premium",
        "ingredients": lines})
    gaming = CandidateFormula.model_validate({
        "product_name": "Renal", "product_format": "premium",
        "ingredients": lines, "overrun_pct": 300.0})

    a = validate_candidate(honest, active_modules=["renal"])
    b = validate_candidate(gaming, active_modules=["renal"])

    assert a.composition.overrun_pct == b.composition.overrun_pct
    assert (a.composition.nutrients_per_serving.potassium_mg
            == b.composition.nutrients_per_serving.potassium_mg)
    assert a.validation.passed == b.validation.passed


def test_model_prose_with_quantities_is_flagged():
    """Prose is the one surface the domain cannot verify, so it must be marked."""
    plain = CandidateFormula.model_validate({
        "product_name": "Plain", "product_format": "standard",
        "ingredients": [{"ref": "milk whole", "percentage": 100}],
        "formulation_notes": "Blend at high shear until smooth."})
    claiming = CandidateFormula.model_validate({
        "product_name": "Claiming", "product_format": "standard",
        "ingredients": [{"ref": "milk whole", "percentage": 100}],
        "formulation_notes": "Provides roughly 200 mg calcium per serving."})

    assert validate_candidate(plain, active_modules=[]).notes_contain_numeric_claims is False
    assert validate_candidate(claiming, active_modules=[]).notes_contain_numeric_claims is True


def test_percentages_in_prose_are_not_flagged():
    """The model may restate its own percentages; those the domain did verify."""
    cand = CandidateFormula.model_validate({
        "product_name": "Pct", "product_format": "standard",
        "ingredients": [{"ref": "milk whole", "percentage": 100}],
        "formulation_notes": "Holding sugar at 12% keeps the texture soft."})
    assert validate_candidate(cand, active_modules=[]).notes_contain_numeric_claims is False


def test_per_line_notes_are_scanned_too():
    cand = CandidateFormula.model_validate({
        "product_name": "Line notes", "product_format": "standard",
        "ingredients": [{"ref": "milk whole", "percentage": 100,
                         "notes": "Contributes about 120 mg potassium."}]})
    assert validate_candidate(cand, active_modules=[]).notes_contain_numeric_claims is True


def test_process_dependent_fields_are_labelled():
    """serving_g and per-serving move with overrun, not with the formula."""
    cand = CandidateFormula.model_validate({
        "product_name": "Labels", "product_format": "premium",
        "ingredients": [{"ref": "milk whole", "percentage": 100}]})
    res = validate_candidate(cand, active_modules=[])
    assert "serving_g" in res.process_dependent_fields
    assert "nutrients_per_serving" in res.process_dependent_fields
    assert "nutrients_per_100g" not in res.process_dependent_fields
