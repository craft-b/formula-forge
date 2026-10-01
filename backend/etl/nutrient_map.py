"""FDC nutrient-number → canonical field mapping.

Nutrient numbers are the stable USDA FoodData Central identifiers (the
`nutrient_nbr` / legacy nutrient_id column in the bulk download), not the
per-download surrogate keys. Energy is resolved with a fallback chain because
Foundation Foods populate different energy calculations per record.

Reference: USDA FDC "Download Data" field descriptions, April 2025 release.
"""
from __future__ import annotations

# canonical field -> FDC nutrient number
NUTRIENT_NUMBERS: dict[str, str] = {
    "protein_g": "1003",
    "fat_g": "1004",
    "carbs_g": "1005",
    "sugars_g": "2000",
    "fiber_g": "1079",
    "sodium_mg": "1093",
    "potassium_mg": "1092",
    "phosphorus_mg": "1091",
    "calcium_mg": "1087",
    "water_g": "1051",
}

# Energy (kcal) resolution order: direct kcal, then Atwater specific, then general.
ENERGY_NUMBERS: tuple[str, ...] = ("1008", "2048", "2047")

# Macros that legitimately default to 0.0 when a record omits them. A pure fat
# carries no protein/carbohydrate; a refined sugar carries no fat; some FDC
# Foundation Foods omit a macro row entirely (e.g. butter has no protein row).
# Water is never zero-defaulted — it is required for total-solids math and its
# absence signals a genuinely malformed source record.
#
# sugars_g is deliberately absent: see RULESET_GATED_FIELDS below.
DEFAULT_ZERO_FIELDS: frozenset[str] = frozenset(
    {"protein_g", "fat_g", "carbs_g", "fiber_g"}
)

# The minerals the clinical rulesets gate on. "Absent" and "zero" are different
# claims for these, and only one of them is safe to guess. A missing row in a
# source record means the lab did not report it, not that the food contains
# none — and substituting zero moves the number in the direction that makes a
# formula look compliant.
#
# This is not hypothetical. egg_yolk was built from FDC 748236, whose 48
# nutrient rows include no minerals at all, so it shipped with phosphorus 0.0
# against a real value near 400 mg/100 g — on the nutrient the renal ruleset
# checks. A curated entry may still assert a zero, because a human wrote it
# down; an FDC-sourced one may not have it inferred.
CLINICAL_MINERAL_FIELDS: frozenset[str] = frozenset(
    {"sodium_mg", "potassium_mg", "phosphorus_mg", "calcium_mg"}
)

# Every field a ruleset gates on, where a guessed zero errs toward compliance.
# Total sugars joined the minerals after the same failure: five FDC dairy
# records (heavy cream, skim, 2 %, buttermilk, cream cheese) report carbohydrate
# but no sugars row, so they shipped with 0.0 g sugars while their own curated
# lactose_g said 2.8-5.0 g. The diabetic ruleset caps sugars per serving, and a
# skim-based formula at ~8.7 g passed as ~5.2 g. An FDC row missing one of these
# must carry an explicit `nutrient_overrides` entry, or the build stops.
RULESET_GATED_FIELDS: frozenset[str] = CLINICAL_MINERAL_FIELDS | {"sugars_g"}

# Canonical nutrient field order for the governed dataset.
NUTRIENT_FIELDS: tuple[str, ...] = (
    "energy_kcal", "protein_g", "fat_g", "carbs_g", "sugars_g", "fiber_g",
    "sodium_mg", "potassium_mg", "phosphorus_mg", "calcium_mg", "water_g",
)
