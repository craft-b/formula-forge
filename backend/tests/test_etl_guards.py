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
            _resolve_nutrients(ing, {"999999": dict(_MACROS_ONLY)})

    def test_the_error_says_what_to_do(self):
        ing = _ingredient(fdc_id=999999)
        with pytest.raises(ValueError) as exc:
            _resolve_nutrients(ing, {"999999": dict(_MACROS_ONLY)})
        message = str(exc.value)
        assert "curated" in message and "fdc_id" in message

    def test_fdc_row_with_minerals_builds(self):
        complete = dict(_MACROS_ONLY, sodium_mg=66.0, potassium_mg=102.0,
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
