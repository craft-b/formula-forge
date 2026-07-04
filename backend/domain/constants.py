"""Frozen-dessert domain constants and v1 physics coefficients.

Every value here is a documented, defensible engineering constant — not a tuned
parameter. Where a value is a v1 approximation it is labeled as such. These
drive the deterministic composition math in `composition.py`; nothing here is
LLM-derived.
"""
from __future__ import annotations

# ── Mass balance ──────────────────────────────────────────────────────────────
MASS_BALANCE_TARGET = 100.0
MASS_BALANCE_TOL = 0.01  # percentage points; Σ ingredients must equal 100 ± tol
MIN_INGREDIENTS = 2
MAX_INGREDIENTS = 12
MIN_PCT = 0.0  # exclusive lower bound enforced in model (>0)
MAX_PCT = 100.0

# ── Serving / overrun (FDA RACC basis for frozen desserts) ────────────────────
# RACC for ice cream / frozen dessert = 2/3 cup ≈ 158 mL.
RACC_VOLUME_ML = 158.0
# Unfrozen mix density (g/mL), typical ice-cream mix ~1.05–1.12.
MIX_DENSITY_G_PER_ML = 1.10
# Per-format default overrun (volume fraction of air added). Overrun is an input;
# these are defaults when the brief does not specify one.
DEFAULT_OVERRUN: dict[str, float] = {
    "premium": 0.25,
    "gelato": 0.25,
    "standard": 1.00,
    "soft_serve": 0.40,
    "novelty": 0.30,
}
DEFAULT_FORMAT = "standard"

# ── Physical-plausibility bands (per 100 g mix, w/w) ──────────────────────────
# Standard ice-cream mix envelope (Goff & Hartel, Ice Cream, 7th ed.).
TOTAL_SOLIDS_BAND = (34.0, 46.0)   # % ; below ~34 = icy/thin, above ~46 = heavy/gummy
FAT_BAND = (0.0, 20.0)             # % ; SOI ice cream ≥10, but low-fat modules go lower
MSNF_BAND = (6.0, 14.0)            # % ; lactose-sandiness risk climbs past ~11–12
STABILIZER_BAND = (0.0, 1.0)      # % total gums+emulsifiers
# PAC (freezing-point-depression), sucrose-equivalent grams per 100 g mix.
PAC_BAND = (22.0, 34.0)            # scoopable tub band; higher = soft/weepy, lower = brick
# POD (sweetness), sucrose-equivalent % per 100 g mix.
POD_BAND = (12.0, 18.0)
# Lactose ceiling before sandiness risk (g per 100 g mix).
LACTOSE_SANDINESS_CEILING = 11.0

# ── PAC / POD model (v1) ──────────────────────────────────────────────────────
# Sweetener-class roles whose *carbohydrate solids* are freezing/sweetening
# active and scale by the ingredient's stored pac/pod factor (sucrose = 100).
SWEETENER_ROLES = frozenset({"sweetener", "polyol", "bulking_fiber"})
HIGH_INTENSITY_ROLE = "high_intensity"
# Lactose is freezing-active (PAC factor ~100) and weakly sweet (POD ~16).
LACTOSE_PAC_FACTOR = 100.0
LACTOSE_POD_FACTOR = 16.0

# Roles considered dairy-derived for MSNF accounting.
DAIRY_ROLES = frozenset({"dairy_base", "dairy_fat", "dairy_solids"})

# ── Scoopability index (v1, model-estimated — NOT a hard rule) ────────────────
# Transparent triangular score peaking at the PAC band centre.
SCOOP_IDEAL_PAC = sum(PAC_BAND) / 2
