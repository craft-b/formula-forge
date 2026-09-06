"""Governed-dataset integrity tests (audit findings F1, F3).

These run in CI against the committed domain/data/ingredients.json and guard the
data foundation: no duplicates, complete nutrient vectors, functional block and
provenance present. If the ETL regresses or a hand-edit corrupts the file, CI
fails here rather than at runtime.
"""
import json
import os

import pytest

from etl.curated_ingredients import CURATED_INGREDIENTS
from etl.nutrient_map import NUTRIENT_FIELDS

_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                     "domain", "data", "ingredients.json")


@pytest.fixture(scope="module")
def dataset():
    with open(_DATA, encoding="utf-8") as f:
        return json.load(f)


def test_dataset_exists_and_versioned(dataset):
    assert dataset["dataset_version"]
    assert dataset["ingredient_count"] == len(dataset["ingredients"])


def test_count_matches_curated_source(dataset):
    assert dataset["ingredient_count"] == len(CURATED_INGREDIENTS)


def test_ingredient_ids_unique(dataset):
    ids = [i["id"] for i in dataset["ingredients"]]
    assert len(ids) == len(set(ids)), "duplicate ingredient ids"


def test_names_unique(dataset):
    names = [i["name"] for i in dataset["ingredients"]]
    assert len(names) == len(set(names)), "duplicate ingredient names"


def test_every_ingredient_has_complete_nutrient_vector(dataset):
    for ing in dataset["ingredients"]:
        vec = ing["nutrients_per_100g"]
        assert set(vec.keys()) == set(NUTRIENT_FIELDS), ing["id"]
        for field, val in vec.items():
            assert isinstance(val, (int, float)), f"{ing['id']}.{field}"
            assert val >= 0, f"{ing['id']}.{field} negative"


def test_nutrient_values_physically_bounded(dataset):
    # per-100g gram macros cannot exceed 100 g; water likewise.
    for ing in dataset["ingredients"]:
        vec = ing["nutrients_per_100g"]
        for field in ("protein_g", "fat_g", "carbs_g", "sugars_g", "fiber_g", "water_g"):
            assert vec[field] <= 100.0, f"{ing['id']}.{field} > 100g"


def test_functional_block_present_and_typed(dataset):
    for ing in dataset["ingredients"]:
        fn = ing["functional"]
        assert isinstance(fn["pac"], (int, float)), ing["id"]
        assert isinstance(fn["pod"], (int, float)), ing["id"]
        assert isinstance(fn["allergens"], list), ing["id"]
        assert "lactose_g" in fn, ing["id"]


def test_provenance_present_and_fdc_linked(dataset):
    for ing in dataset["ingredients"]:
        prov = ing["provenance"]
        assert prov["source"] in {"FDC_foundation_food", "curated"}, ing["id"]
        if prov["source"] == "FDC_foundation_food":
            assert prov["fdc_id"] is not None, ing["id"]


def test_no_nutrient_free_rows_regression(dataset):
    # The old usda_foods.json was names-only (F1). Assert the new dataset is not.
    keys = set()
    for ing in dataset["ingredients"]:
        keys.update(ing["nutrients_per_100g"].keys())
    assert "phosphorus_mg" in keys and "potassium_mg" in keys


def test_covers_all_constraint_module_needs(dataset):
    # Every v1 constraint module needs at least one enabling ingredient class.
    roles = {i["role"] for i in dataset["ingredients"]}
    for required in ("dairy_fat", "protein", "sweetener", "polyol",
                     "stabilizer", "fat", "base"):
        assert required in roles, f"no ingredient with role '{required}'"


# ── Clinically-gated minerals ─────────────────────────────────────────────────
# egg_yolk was built from FDC 748236, a Foundation Food whose 48 nutrient rows
# contain no minerals at all. The ETL treated "absent" as "zero", so the library
# shipped a yolk with phosphorus 0.0 where the real figure is near 400 mg/100 g
# — silently, on the nutrient the renal ruleset gates. Every formula containing
# egg yolk under-reported phosphorus and looked more compliant than it was.

_CLINICAL_MINERALS = ("sodium_mg", "potassium_mg", "phosphorus_mg", "calcium_mg")


def test_no_fdc_row_has_an_all_zero_mineral_profile(dataset):
    """A real food measured against a real record has some mineral content.

    All four reading zero on an FDC-sourced row means the source omitted them
    and something substituted a number, which is the defect this guards.
    """
    offenders = [
        ing["id"] for ing in dataset["ingredients"]
        if ing["provenance"]["source"] != "curated"
        and all(ing["nutrients_per_100g"][m] == 0.0 for m in _CLINICAL_MINERALS)
    ]
    assert not offenders, (
        f"FDC-sourced ingredients with every clinical mineral at zero: {offenders}. "
        "Point fdc_id at a record that reports them, or add a curated override."
    )


def test_egg_yolk_reports_its_phosphorus(dataset):
    """The specific row that was wrong, pinned by name."""
    yolk = next(i for i in dataset["ingredients"] if i["id"] == "egg_yolk")
    phosphorus = yolk["nutrients_per_100g"]["phosphorus_mg"]
    # Egg yolk is one of the most phosphorus-dense ordinary foods; anything near
    # zero means the mineral rows went missing again.
    assert phosphorus > 300, f"egg_yolk phosphorus is {phosphorus} mg/100 g"


def test_curated_rows_may_still_assert_a_zero(dataset):
    """The guard must not force nonsense onto refined ingredients.

    A refined oil or a crystalline sweetener genuinely contains no measurable
    minerals, and a curated row is a human writing that down.
    """
    curated_zeros = [
        ing["id"] for ing in dataset["ingredients"]
        if ing["provenance"]["source"] == "curated"
        and all(ing["nutrients_per_100g"][m] == 0.0 for m in _CLINICAL_MINERALS)
    ]
    assert curated_zeros, "expected some curated rows to legitimately carry zeros"
