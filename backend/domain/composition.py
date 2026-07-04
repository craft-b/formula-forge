"""Deterministic composition math (pure — no I/O, no framework).

Given resolved ingredient lines (each an `IngredientSpec` + a percentage), this
module computes the full nutrient vector, physical indices (total solids, fat,
MSNF, sugars), PAC/POD, per-serving values, and a transparent scoopability
index. These are the ONLY numbers the product shows a user. LLM-supplied
numbers never enter here — the pipeline discards them before this point.

All functions are pure and linear in the ingredient percentages, which makes
their invariants (non-negativity, additivity, scale behaviour) property-testable.
"""
from __future__ import annotations

from . import constants as C
from .models import ComputedComposition, IngredientSpec, NutrientVector

_NUTRIENT_FIELDS = tuple(NutrientVector.model_fields.keys())


def _weighted_nutrients(lines: list[tuple[IngredientSpec, float]]) -> dict[str, float]:
    """Mass-weighted nutrient vector per 100 g of mix.

    Each ingredient contributes (percentage / 100) of its per-100 g vector.
    Linear by construction: doubling a percentage doubles its contribution.
    """
    totals = {f: 0.0 for f in _NUTRIENT_FIELDS}
    for spec, pct in lines:
        frac = pct / 100.0
        vec = spec.nutrients_per_100g
        for f in _NUTRIENT_FIELDS:
            totals[f] += frac * getattr(vec, f)
    return {f: round(v, 3) for f, v in totals.items()}


def _pac_pod_totals(lines: list[tuple[IngredientSpec, float]]) -> tuple[float, float]:
    """PAC (freezing-point depression) and POD (sweetness), sucrose-equivalent.

    v1 model (documented in constants.py):
      * Sweetener-class roles: carbohydrate solids scale by the ingredient's
        stored pac/pod factor (sucrose = 100).
      * Dairy lactose is freezing-active (factor ~100) and weakly sweet (~16).
      * High-intensity sweeteners contribute sweetness by potency, ~zero mass.
    """
    pac = 0.0
    pod = 0.0
    for spec, pct in lines:
        frac = pct / 100.0
        fn = spec.functional
        if spec.role in C.SWEETENER_ROLES:
            solids = spec.nutrients_per_100g.carbs_g
            pac += frac * solids * (fn.pac / 100.0)
            pod += frac * solids * (fn.pod / 100.0)
        elif spec.role == C.HIGH_INTENSITY_ROLE:
            # Potency-dosed: sweetness ~ inclusion × factor; negligible PAC.
            pod += frac * fn.pod / 100.0
        # Lactose contribution (any dairy-derived ingredient).
        lactose = fn.lactose_g
        if lactose:
            pac += frac * lactose * (C.LACTOSE_PAC_FACTOR / 100.0)
            pod += frac * lactose * (C.LACTOSE_POD_FACTOR / 100.0)
    return round(pac, 3), round(pod, 3)


def _msnf_pct(lines: list[tuple[IngredientSpec, float]]) -> float:
    """Milk-solids-not-fat, % of mix (v1 proxy).

    MSNF ≈ dairy-derived (protein + lactose) solids. A first-order proxy that
    omits the small mineral/ash term; documented as v1.
    """
    msnf = 0.0
    for spec, pct in lines:
        if spec.role in C.DAIRY_ROLES or (spec.functional.protein_type or "").startswith("dairy"):
            frac = pct / 100.0
            msnf += frac * (spec.nutrients_per_100g.protein_g + spec.functional.lactose_g)
    return round(msnf, 3)


def _lactose_pct(lines: list[tuple[IngredientSpec, float]]) -> float:
    return round(sum((pct / 100.0) * spec.functional.lactose_g for spec, pct in lines), 3)


def _stabilizer_pct(lines: list[tuple[IngredientSpec, float]]) -> float:
    return round(sum(pct for spec, pct in lines
                     if spec.functional.stabilizer_class in {"galactomannan", "carrageenan", "emulsifier"}), 3)


def _cost_per_kg(lines: list[tuple[IngredientSpec, float]]) -> float:
    return round(sum((pct / 100.0) * spec.functional.cost_per_kg_usd for spec, pct in lines), 2)


def _allergens(lines: list[tuple[IngredientSpec, float]]) -> list[str]:
    found: set[str] = set()
    for spec, _ in lines:
        found.update(spec.functional.allergens)
    return sorted(found)


def _scoopability_index(pac_total: float) -> float:
    """Transparent triangular index (0–100) peaking at the PAC band centre.

    MODEL-ESTIMATED, not a hard rule. Far from the ideal PAC → harder or softer
    than ideal scoopability at serving temperature.
    """
    lo, hi = C.PAC_BAND
    half_width = (hi - lo) / 2 + 6.0  # tolerance beyond the band before index hits 0
    dist = abs(pac_total - C.SCOOP_IDEAL_PAC)
    return round(max(0.0, 100.0 * (1 - dist / half_width)), 1)


def serving_grams(overrun_pct: float) -> float:
    """Grams of mix in one RACC serving at the given overrun.

    A RACC volume of frozen product contains mix + air; air is weightless, so
    grams of mix per serving = RACC_volume / (1 + overrun) × mix_density.
    """
    overrun = overrun_pct / 100.0
    return round(C.RACC_VOLUME_ML / (1.0 + overrun) * C.MIX_DENSITY_G_PER_ML, 2)


def resolve_overrun(product_format: str, overrun_pct: float | None) -> float:
    if overrun_pct is not None:
        return float(overrun_pct)
    return C.DEFAULT_OVERRUN.get(product_format, C.DEFAULT_OVERRUN[C.DEFAULT_FORMAT]) * 100.0


def compute_composition(
    lines: list[tuple[IngredientSpec, float]],
    product_format: str = C.DEFAULT_FORMAT,
    overrun_pct: float | None = None,
) -> ComputedComposition:
    """Compute the full deterministic composition for a set of resolved lines."""
    overrun = resolve_overrun(product_format, overrun_pct)
    per_100g = _weighted_nutrients(lines)
    serving_g = serving_grams(overrun)
    scale = serving_g / 100.0
    per_serving = {f: round(v * scale, 3) for f, v in per_100g.items()}

    pac_total, pod_total = _pac_pod_totals(lines)
    total_solids = round(100.0 - per_100g["water_g"], 3)

    return ComputedComposition(
        nutrients_per_100g=NutrientVector(**per_100g),
        nutrients_per_serving=NutrientVector(**per_serving),
        serving_g=serving_g,
        overrun_pct=round(overrun, 2),
        product_format=product_format,
        total_solids_pct=total_solids,
        fat_pct=per_100g["fat_g"],
        msnf_pct=_msnf_pct(lines),
        sugars_pct=per_100g["sugars_g"],
        lactose_pct=_lactose_pct(lines),
        stabilizer_pct=_stabilizer_pct(lines),
        pac_total=pac_total,
        pod_total=pod_total,
        scoopability_index=_scoopability_index(pac_total),
        total_cost_per_kg_usd=_cost_per_kg(lines),
        allergens=_allergens(lines),
    )


def mass_balance_error(percentages: list[float]) -> float:
    """Absolute deviation of the ingredient sum from 100%."""
    return abs(sum(percentages) - C.MASS_BALANCE_TARGET)


def mass_balance_ok(percentages: list[float]) -> bool:
    return mass_balance_error(percentages) <= C.MASS_BALANCE_TOL
