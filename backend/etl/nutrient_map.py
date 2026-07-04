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

# Nutrients that legitimately default to 0.0 when a record omits them. A pure
# fat carries no protein/carbohydrate; a refined sugar carries no fat; some FDC
# Foundation Foods omit a macro row entirely (e.g. butter has no protein row).
# Only water is never zero-defaulted — it is required for total-solids math and
# its absence signals a genuinely malformed source record.
DEFAULT_ZERO_FIELDS: frozenset[str] = frozenset(
    {"protein_g", "fat_g", "carbs_g", "sugars_g", "fiber_g",
     "sodium_mg", "potassium_mg", "phosphorus_mg", "calcium_mg"}
)

# Canonical nutrient field order for the governed dataset.
NUTRIENT_FIELDS: tuple[str, ...] = (
    "energy_kcal", "protein_g", "fat_g", "carbs_g", "sugars_g", "fiber_g",
    "sodium_mg", "potassium_mg", "phosphorus_mg", "calcium_mg", "water_g",
)
