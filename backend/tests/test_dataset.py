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
