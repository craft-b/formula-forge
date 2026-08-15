"""Pydantic models for the FormulaForge domain (pure — no I/O, no framework).

Trust boundary encoded in types:

  * `CandidateFormula` is what the LLM proposes. It carries **structure only** —
    ingredients and percentages — and deliberately has **no nutrition fields**.
    The LLM cannot assert a calorie or a milligram of potassium; those are
    computed downstream by `composition.py` from the governed ingredient library.
  * `ComputedComposition` is what the domain calculates.
  * `ValidatedFormula` is what a user is allowed to see: proposal + computed
    composition + validation report, with every number provenance-labelled.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Governed ingredient library ───────────────────────────────────────────────

class NutrientVector(BaseModel):
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    sugars_g: float
    fiber_g: float
    sodium_mg: float
    potassium_mg: float
    phosphorus_mg: float
    calcium_mg: float
    water_g: float


class FunctionalProps(BaseModel):
    pac: float
    pod: float
    fat_type: Optional[str] = None
    protein_type: Optional[str] = None
    stabilizer_class: Optional[str] = None
    lactose_g: float = 0.0
    allergens: list[str] = Field(default_factory=list)
    cost_per_kg_usd: float = 0.0


class IngredientSpec(BaseModel):
    id: str
    name: str
    role: str
    nutrients_per_100g: NutrientVector
    functional: FunctionalProps
    provenance: dict = Field(default_factory=dict)


# ── LLM proposal (structure only) ─────────────────────────────────────────────

class FormulaIngredient(BaseModel):
    """One line of a proposed formula. `ref` is the LLM's ingredient name or id;
    it must resolve to a governed library ingredient during validation."""
    ref: str = Field(..., min_length=1)
    percentage: float = Field(..., gt=0.0, le=100.0)
    notes: str = ""


class CandidateFormula(BaseModel):
    """The LLM's proposal. No nutrition fields by construction (see module doc).

    Deliberately carries no `overrun_pct`. Overrun sets how many grams of mix
    are in a serving, so it is the divisor on every per-serving value — and
    per-serving is the basis every clinical limit is checked against. A
    model-supplied overrun would therefore let the model scale the numbers that
    decide compliance. Overrun is derived from `product_format`, which the user
    controls, or passed explicitly to `validate_candidate` by the caller.
    """
    type: Literal["formula"] = "formula"
    product_name: str = Field(..., min_length=1)
    description: str = ""
    product_format: str = "standard"
    ingredients: list[FormulaIngredient] = Field(..., min_length=1)
    formulation_notes: str = ""

    @field_validator("ingredients")
    @classmethod
    def _cap_ingredient_count(cls, v):
        if len(v) > 24:
            raise ValueError("too many ingredients (max 24)")
        return v


# ── Domain computation output ─────────────────────────────────────────────────

class ResolvedLine(BaseModel):
    """A candidate line successfully matched to a library ingredient."""
    ref: str
    ingredient_id: str
    ingredient_name: str
    percentage: float
    notes: str = ""


class ComputedComposition(BaseModel):
    """Everything the domain calculates. Sole source of user-facing numbers."""
    nutrients_per_100g: NutrientVector
    nutrients_per_serving: NutrientVector
    serving_g: float
    overrun_pct: float
    product_format: str
    total_solids_pct: float
    fat_pct: float
    msnf_pct: float
    sugars_pct: float
    lactose_pct: float
    stabilizer_pct: float
    pac_total: float
    pod_total: float
    scoopability_index: float  # empirical index, not mass balance; 0–100
    total_cost_per_kg_usd: float
    allergens: list[str]


# ── Validation ────────────────────────────────────────────────────────────────

Severity = Literal["error", "warn"]


class Violation(BaseModel):
    rule_id: str
    severity: Severity
    measured: Optional[float] = None
    limit: Optional[float] = None
    explanation: str


class ValidationReport(BaseModel):
    passed: bool           # True only if there are no error-severity violations
    repaired: bool = False
    violations: list[Violation] = Field(default_factory=list)
    active_modules: list[str] = Field(default_factory=list)


class ValidatedFormula(BaseModel):
    """The only object permitted to reach the user."""
    type: Literal["formula"] = "formula"
    product_name: str
    description: str = ""
    product_format: str
    ingredients: list[ResolvedLine]
    composition: ComputedComposition
    validation: ValidationReport
    formulation_notes: str = ""
    # Provenance labels for the UI's rule-verified vs model-estimated surface.
    verified_fields: list[str] = Field(default_factory=list)
    estimated_fields: list[str] = Field(default_factory=list)
    # Verified, but also a function of the overrun assumption rather than of
    # the formula alone. Same ingredients at a different product format give
    # different values here.
    process_dependent_fields: list[str] = Field(default_factory=list)
    # True when model-authored prose (formulation_notes, per-line notes)
    # contains a quantity. Those numbers are not computed by the domain and
    # must not be presented as if they were.
    notes_contain_numeric_claims: bool = False


class RejectedFormula(BaseModel):
    """Returned when a proposal cannot be made compliant (still explains why)."""
    type: Literal["rejection"] = "rejection"
    product_name: str
    reason: str
    violations: list[Violation] = Field(default_factory=list)
    unresolved_ingredients: list[str] = Field(default_factory=list)
