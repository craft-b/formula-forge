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


# ── Mass conservation ─────────────────────────────────────────────────────────


def test_no_ingredient_contains_more_than_100g_per_100g(dataset):
    """water + protein + fat + carbohydrate cannot exceed the ingredient itself.

    total_solids is computed as 100 - water, and PAC/POD scale off carbs, so a
    row that overstates both is internally inconsistent in two directions at
    once. Three rows did: dextrose monohydrate summed to 109 g (carbs left at
    100 when 9 g of the crystal is water), and guar and locust bean gum to 103.5
    and 104.6.

    The bound is 100.5 rather than 100 to absorb rounding, not to leave room.
    """
    offenders = []
    for ing in dataset["ingredients"]:
        n = ing["nutrients_per_100g"]
        total = n["water_g"] + n["protein_g"] + n["fat_g"] + n["carbs_g"]
        if total > 100.5:
            offenders.append((ing["id"], round(total, 1)))
    assert not offenders, f"rows summing past 100 g per 100 g: {offenders}"


# Sugars and fibre are subsets of carbohydrate, so neither should exceed it —
# but USDA computes carbohydrate *by difference* (100 minus water, protein, fat
# and ash) while measuring sugars directly, so the two carry different errors and
# dairy inverts slightly. Whole milk is the real case: lactose 5.05 g against
# carbohydrate 4.80 g, which is what USDA itself reports. The tolerance absorbs
# that methodological artefact and nothing larger; a gross inversion, such as a
# sweetener row with sugars far above its carbohydrate, still fails.
_CARB_SUBSET_TOLERANCE_G = 0.5


def test_sugars_and_fiber_do_not_exceed_carbohydrate(dataset):
    offenders = []
    for ing in dataset["ingredients"]:
        n = ing["nutrients_per_100g"]
        ceiling = n["carbs_g"] + _CARB_SUBSET_TOLERANCE_G
        if n["sugars_g"] > ceiling or n["fiber_g"] > ceiling:
            offenders.append(
                (ing["id"], n["carbs_g"], n["sugars_g"], n["fiber_g"]))
    assert not offenders, f"(id, carbs, sugars, fiber) inconsistent: {offenders}"


# ── Allergens ─────────────────────────────────────────────────────────────────
# These are not documentation. The vegan ruleset blacklists "milk" and "egg" and
# raises an *error*, which is what makes a formula fail. It also blacklists the
# dairy and egg roles — but whey_protein_isolate and micellar_casein carry the
# role "protein", so for those two the allergen field is the only thing standing
# between a dairy protein and a formula labelled vegan.
#
# Nothing checked this field, and the ways it can go wrong are quiet: an omitted
# allergen, or a misspelling such as "diary", never matches the blacklist and so
# never raises. The formula simply passes.

_DAIRY_ALLERGEN = "milk"
# Closed vocabulary. A value outside it cannot match any ruleset blacklist, so a
# typo disables the guard silently rather than failing.
_KNOWN_ALLERGENS = {"milk", "egg", "soy", "tree_nut", "peanut", "wheat", "sesame"}


def _is_dairy(ing) -> bool:
    f = ing["functional"]
    return (
        ing["role"].startswith("dairy")
        or (f.get("protein_type") or "").startswith("dairy")
        or f.get("fat_type") == "dairy"
        or f["lactose_g"] > 0
    )


def test_allergen_vocabulary_is_closed(dataset):
    used = {a for ing in dataset["ingredients"] for a in ing["functional"]["allergens"]}
    unknown = sorted(used - _KNOWN_ALLERGENS)
    assert not unknown, (
        f"unrecognised allergen labels {unknown}: a label no ruleset blacklists "
        "cannot raise, so a misspelling silently disables the check"
    )


def test_every_dairy_ingredient_declares_milk(dataset):
    offenders = [
        ing["id"] for ing in dataset["ingredients"]
        if _is_dairy(ing) and _DAIRY_ALLERGEN not in ing["functional"]["allergens"]
    ]
    assert not offenders, f"dairy ingredients without a milk allergen: {offenders}"


def test_no_milk_allergen_without_a_dairy_signal(dataset):
    """The converse, so the check cannot be satisfied by labelling everything."""
    offenders = [
        ing["id"] for ing in dataset["ingredients"]
        if _DAIRY_ALLERGEN in ing["functional"]["allergens"] and not _is_dairy(ing)
    ]
    assert not offenders, f"milk allergen with no dairy signal: {offenders}"


def test_egg_and_soy_proteins_declare_their_allergen(dataset):
    offenders = []
    for ing in dataset["ingredients"]:
        protein = ing["functional"].get("protein_type") or ""
        allergens = ing["functional"]["allergens"]
        if protein == "egg" and "egg" not in allergens:
            offenders.append((ing["id"], "egg"))
        if protein == "soy" and "soy" not in allergens:
            offenders.append((ing["id"], "soy"))
    assert not offenders, f"protein type without its allergen: {offenders}"


def test_lactose_implies_milk(dataset):
    offenders = [
        ing["id"] for ing in dataset["ingredients"]
        if ing["functional"]["lactose_g"] > 0
        and _DAIRY_ALLERGEN not in ing["functional"]["allergens"]
    ]
    assert not offenders, f"lactose present but no milk allergen: {offenders}"


def test_allergen_rule_is_what_stops_dairy_protein_in_a_vegan_formula():
    """Behavioural proof that this data is load-bearing.

    whey_protein_isolate's role is "protein", which the vegan ruleset does not
    blacklist. Only its milk allergen rejects the formula, so the field cannot be
    treated as descriptive metadata.
    """
    from domain import CandidateFormula, validate_candidate

    candidate = CandidateFormula.model_validate({
        "product_name": "Vegan?", "product_format": "premium",
        "ingredients": [
            {"ref": "almond milk unsweetened", "percentage": 70},
            {"ref": "coconut cream", "percentage": 18},
            {"ref": "whey protein isolate", "percentage": 6},
            {"ref": "sucrose", "percentage": 6},
        ]})
    result = validate_candidate(candidate, active_modules=["vegan"])

    assert result.type == "formula"
    assert result.validation.passed is False
    errors = {v.rule_id for v in result.validation.violations if v.severity == "error"}
    assert "vegan.allergen.milk" in errors, (
        f"expected the allergen rule to reject this formula; errors were {errors}")
