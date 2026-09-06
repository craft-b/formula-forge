"""ETL: build the governed frozen-dessert ingredient library.

Reads the USDA FoodData Central bulk download (`backend/data/food.csv`,
`food_nutrient.csv`), pulls a real nutrient vector for every curated ingredient
that carries an `fdc_id`, merges it with the curated functional properties in
`curated_ingredients.py`, and writes a versioned, governed dataset to
`backend/domain/data/ingredients.json`.

This restores the data lineage the deleted `prep_data.py` used to provide, and
replaces the names-only `usda_foods.json` (audit findings F1, F3).

Run from `backend/`:
    python -m etl.build_ingredients

No network access required — the FDC bulk CSVs are read from disk. The output
JSON is committed; the raw CSVs stay gitignored (they are large and
reproducible from FDC).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date

from etl.curated_ingredients import CURATED_INGREDIENTS
from etl.nutrient_map import (
    CLINICAL_MINERAL_FIELDS,
    DEFAULT_ZERO_FIELDS,
    ENERGY_NUMBERS,
    NUTRIENT_FIELDS,
    NUTRIENT_NUMBERS,
)

DATASET_VERSION = "2026.09.0"
TRANSFORM_VERSION = "etl-1.0.0"

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.dirname(_HERE)
FOOD_CSV = os.path.join(_BACKEND, "data", "food.csv")
FOOD_NUTRIENT_CSV = os.path.join(_BACKEND, "data", "food_nutrient.csv")
OUT_DIR = os.path.join(_BACKEND, "domain", "data")
OUT_PATH = os.path.join(OUT_DIR, "ingredients.json")

# Nutrient rounding (dp) per canonical field.
_ROUND = {f: (2 if f.endswith("_g") or f == "energy_kcal" else 1) for f in NUTRIENT_FIELDS}


def _needed_fdc_ids() -> set[str]:
    return {str(ing["fdc_id"]) for ing in CURATED_INGREDIENTS if ing.get("fdc_id")}


def _load_fdc_nutrients(fdc_ids: set[str]) -> dict[str, dict[str, float]]:
    """Return {fdc_id: {canonical_field: amount}} for the requested foods."""
    if not fdc_ids:
        return {}
    if not os.path.exists(FOOD_NUTRIENT_CSV):
        raise FileNotFoundError(
            f"FDC bulk file not found: {FOOD_NUTRIENT_CSV}\n"
            "Place the FoodData Central bulk download in backend/data/ "
            "(food.csv, food_nutrient.csv) and re-run."
        )

    number_to_field = {num: field for field, num in NUTRIENT_NUMBERS.items()}
    energy_by_food: dict[str, dict[str, float]] = {fid: {} for fid in fdc_ids}
    out: dict[str, dict[str, float]] = {fid: {} for fid in fdc_ids}

    with open(FOOD_NUTRIENT_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row["fdc_id"]
            if fid not in fdc_ids:
                continue
            num = row["nutrient_id"]
            amount = row["amount"]
            if amount == "":
                continue
            val = float(amount)
            if num in number_to_field:
                out[fid][number_to_field[num]] = val
            elif num in ENERGY_NUMBERS:
                energy_by_food[fid][num] = val

    # Resolve energy via the fallback chain (kcal → Atwater specific → general).
    for fid in fdc_ids:
        for num in ENERGY_NUMBERS:
            if num in energy_by_food[fid]:
                out[fid]["energy_kcal"] = energy_by_food[fid][num]
                break
    return out


def _resolve_nutrients(ing: dict, fdc_data: dict[str, dict[str, float]]) -> tuple[dict, dict]:
    """Return (nutrient_vector, provenance) for one ingredient."""
    if ing.get("fdc_id"):
        fid = str(ing["fdc_id"])
        raw = dict(fdc_data.get(fid, {}))
        source = "FDC_foundation_food"
    else:
        raw = dict(ing["nutrients_per_100g"])
        source = "curated"
        fid = None

    vector: dict[str, float] = {}
    for field in NUTRIENT_FIELDS:
        if field == "energy_kcal":
            continue  # resolved after macros so Atwater fallback can run
        if field in raw:
            vector[field] = round(float(raw[field]), _ROUND[field])
        elif field in DEFAULT_ZERO_FIELDS:
            vector[field] = 0.0
        elif field in CLINICAL_MINERAL_FIELDS and source == "curated":
            # A curated row is a human assertion, including an assertion of zero.
            vector[field] = 0.0
        else:
            raise ValueError(
                f"{ing['id']}: source record has no '{field}' row. "
                "Zero is not a safe substitute for a mineral the clinical "
                "rulesets check — it makes a formula look compliant. Either "
                "point fdc_id at a record that reports it, or add an explicit "
                "curated nutrients_per_100g override."
            )

    # Energy: use the FDC/curated value when present, else derive via Atwater
    # general factors (protein 4, fat 9, carbohydrate 4 kcal/g). A handful of
    # Foundation Foods (e.g. butter) carry macros but no energy row.
    energy_derived = False
    if "energy_kcal" in raw:
        vector["energy_kcal"] = round(float(raw["energy_kcal"]), _ROUND["energy_kcal"])
    else:
        vector["energy_kcal"] = round(
            4 * vector["protein_g"] + 9 * vector["fat_g"] + 4 * vector["carbs_g"],
            _ROUND["energy_kcal"],
        )
        energy_derived = True

    provenance = {
        "source": source,
        "fdc_id": ing["fdc_id"] if ing.get("fdc_id") else None,
        "energy_atwater_derived": energy_derived,
        "dataset_version": DATASET_VERSION,
        "transform_version": TRANSFORM_VERSION,
    }
    # Reorder vector to canonical field order.
    vector = {f: vector[f] for f in NUTRIENT_FIELDS}
    return vector, provenance


def build() -> dict:
    fdc_data = _load_fdc_nutrients(_needed_fdc_ids())
    ingredients = []
    seen_ids: set[str] = set()

    for ing in CURATED_INGREDIENTS:
        if ing["id"] in seen_ids:
            raise ValueError(f"duplicate ingredient id: {ing['id']}")
        seen_ids.add(ing["id"])
        vector, provenance = _resolve_nutrients(ing, fdc_data)
        ingredients.append({
            "id": ing["id"],
            "name": ing["name"],
            "role": ing["role"],
            "nutrients_per_100g": vector,
            "functional": ing["functional"],
            "provenance": provenance,
        })

    return {
        "dataset_version": DATASET_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "built": date.today().isoformat(),
        "source": "USDA FoodData Central Foundation Foods (nutrients) + curated "
                  "functional properties (PAC/POD). See etl/curated_ingredients.py.",
        "ingredient_count": len(ingredients),
        "ingredients": ingredients,
    }


def main() -> int:
    dataset = build()
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
        f.write("\n")
    n = dataset["ingredient_count"]
    fdc = sum(1 for i in dataset["ingredients"] if i["provenance"]["source"] != "curated")
    print(f"Wrote {n} ingredients to {os.path.relpath(OUT_PATH, _BACKEND)} "
          f"({fdc} FDC-sourced, {n - fdc} curated), version {DATASET_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
