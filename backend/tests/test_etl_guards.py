"""The ETL guard: absent minerals must stop the build, not become zeros."""
from __future__ import annotations

import pytest

from etl.build_ingredients import _resolve_nutrients

_FUNCTIONAL = {"pac": 0.0, "pod": 0.0, "fat_type": None, "protein_type": None,
               "stabilizer_class": None, "lactose_g": 0.0, "allergens": [],
               "cost_per_kg_usd": 1.0}
# What an FDC record looks like when the lab reported macros but no minerals —
# exactly the shape of FDC 748236, which shipped a phosphorus-free egg yolk.
_MACROS_ONLY = {"protein_g": 16.2, "fat_g": 28.8, "carbs_g": 1.02,
                "water_g": 52.1, "energy_kcal": 334.0}


def _ingredient(**over):
    base = {"id": "probe", "name": "Probe", "role": "egg", "functional": _FUNCTIONAL}
    base.update(over)
    return base


class TestMineralsAreNotInvented:
    def test_fdc_row_missing_minerals_raises(self):
        ing = _ingredient(fdc_id=999999)
        with pytest.raises(ValueError, match="phosphorus_mg|sodium_mg|potassium_mg|calcium_mg"):
            # sugars_g present so the probe isolates the mineral guard.
            _resolve_nutrients(ing, {"999999": dict(_MACROS_ONLY, sugars_g=0.56)})

    def test_the_error_says_what_to_do(self):
        ing = _ingredient(fdc_id=999999)
        with pytest.raises(ValueError) as exc:
            _resolve_nutrients(ing, {"999999": dict(_MACROS_ONLY)})
        message = str(exc.value)
        assert "curated" in message and "fdc_id" in message

    def test_fdc_row_with_minerals_builds(self):
        complete = dict(_MACROS_ONLY, sugars_g=0.56, sodium_mg=66.0, potassium_mg=102.0,
                        phosphorus_mg=443.0, calcium_mg=119.0)
        vector, provenance = _resolve_nutrients(_ingredient(fdc_id=329596),
                                                {"329596": complete})
        assert vector["phosphorus_mg"] == 443.0
        assert provenance["source"] == "FDC_foundation_food"

    def test_curated_row_may_omit_minerals(self):
        """A refined oil has none, and a human said so by curating the row."""
        ing = _ingredient(nutrients_per_100g={"protein_g": 0.0, "fat_g": 100.0,
                                              "carbs_g": 0.0, "water_g": 0.0,
                                              "energy_kcal": 884.0})
        vector, provenance = _resolve_nutrients(ing, {})
        assert vector["phosphorus_mg"] == 0.0
        assert provenance["source"] == "curated"

    def test_missing_water_still_raises_for_curated(self):
        """Water is required for total-solids math and is never defaulted."""
        ing = _ingredient(nutrients_per_100g={"protein_g": 0.0, "fat_g": 100.0,
                                              "carbs_g": 0.0, "energy_kcal": 884.0})
        with pytest.raises(ValueError, match="water_g"):
            _resolve_nutrients(ing, {})


# What a Foundation Foods dairy record looks like: carbohydrate by difference,
# minerals reported, no total-sugars row (FDC 322559, skim milk).
_DAIRY_NO_SUGARS = dict(_MACROS_ONLY, sodium_mg=41.0, potassium_mg=167.0,
                        phosphorus_mg=107.0, calcium_mg=122.0)


class TestSugarsAreNotInvented:
    """Sugars is ruleset-gated (diabetic), so it gets the minerals' rule."""

    def test_fdc_row_missing_sugars_raises(self):
        ing = _ingredient(fdc_id=322559)
        with pytest.raises(ValueError, match="sugars_g"):
            _resolve_nutrients(ing, {"322559": dict(_DAIRY_NO_SUGARS)})

    def test_override_fills_the_gap_and_is_labelled(self):
        ing = _ingredient(fdc_id=322559, nutrient_overrides={"sugars_g": 5.0})
        vector, provenance = _resolve_nutrients(ing, {"322559": dict(_DAIRY_NO_SUGARS)})
        assert vector["sugars_g"] == 5.0
        assert provenance["curated_overrides"] == ["sugars_g"]
        assert provenance["source"] == "FDC_foundation_food"

    def test_stale_override_raises(self):
        """An override for a value FDC does report would silently shadow it."""
        ing = _ingredient(fdc_id=322559, nutrient_overrides={"sugars_g": 5.0})
        with pytest.raises(ValueError, match="stale"):
            _resolve_nutrients(ing, {"322559": dict(_DAIRY_NO_SUGARS, sugars_g=4.9)})

    def test_unknown_override_field_raises(self):
        ing = _ingredient(fdc_id=322559, nutrient_overrides={"sugar_g": 5.0})
        with pytest.raises(ValueError, match="unknown nutrient override"):
            _resolve_nutrients(ing, {"322559": dict(_DAIRY_NO_SUGARS)})


def test_skim_based_diabetic_formula_is_no_longer_a_false_pass():
    """The formula that passed at ~5.2 g sugars/serving while really ~8.7 g.

    Lactose from 72 % skim and 14 % cream was counted as zero, which put a
    formula over the diabetic cap on the compliant side of it.
    """
    from domain import CandidateFormula, validate_candidate

    candidate = CandidateFormula(
        product_name="Skim diabetic probe", description="", product_format="standard",
        formulation_notes="",
        ingredients=[
            {"ref": "Milk, nonfat / skim", "percentage": 72},
            {"ref": "Cream, heavy (36% fat)", "percentage": 14},
            {"ref": "Sucrose (table sugar)", "percentage": 6},
            {"ref": "Polydextrose (bulking fiber)", "percentage": 6},
            {"ref": "Whey protein isolate (90%)", "percentage": 1.5},
            {"ref": "Guar gum", "percentage": 0.3},
            {"ref": "Locust bean gum", "percentage": 0.2},
        ],
    )
    result = validate_candidate(candidate, active_modules=["diabetic"])
    assert result.composition.nutrients_per_serving.sugars_g > 8.0
    assert not result.validation.passed
    assert any(v.rule_id == "diabetic.sugars" for v in result.validation.violations)
