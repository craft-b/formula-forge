"""The single path from an LLM proposal to a user-facing formula.

`validate_candidate` is the ONLY function the API layer calls to turn a
`CandidateFormula` (LLM structure proposal) into something a user may see. It
resolves ingredients against the governed library, discards any LLM-supplied
numbers (there are none in the model by construction), computes the composition
deterministically, runs a bounded mass-balance repair, and validates. There is
no other route from generation to the client — enforced by an integration test.
"""
from __future__ import annotations

from . import constants as C
from .composition import compute_composition, mass_balance_error
from .models import (
    CandidateFormula,
    ComputedComposition,
    RejectedFormula,
    ResolvedLine,
    ValidatedFormula,
    Violation,
)
from .repository import IngredientRepository, get_repository
from .validator import validate

# Fields whose values are rule-verified (deterministically computed) vs
# model-estimated. Surfaced to the UI so users know what is which.
_VERIFIED_FIELDS = [
    "nutrients_per_100g", "nutrients_per_serving", "total_solids_pct", "fat_pct",
    "msnf_pct", "sugars_pct", "lactose_pct", "pac_total", "pod_total",
    "serving_g", "total_cost_per_kg_usd", "allergens",
]
_ESTIMATED_FIELDS = ["scoopability_index"]

_UNREPAIRABLE_ERROR = 40.0  # percentage points off 100 beyond which we reject


def validate_candidate(
    candidate: CandidateFormula,
    active_modules: list[str] | None = None,
    repo: IngredientRepository | None = None,
) -> ValidatedFormula | RejectedFormula:
    active_modules = active_modules or []
    repo = repo or get_repository()

    # 1. Resolve every ingredient to the governed library. No phantoms.
    resolved: list[ResolvedLine] = []
    specs = []
    unresolved: list[str] = []
    for line in candidate.ingredients:
        spec = repo.resolve(line.ref)
        if spec is None:
            unresolved.append(line.ref)
            continue
        resolved.append(ResolvedLine(
            ref=line.ref, ingredient_id=spec.id, ingredient_name=spec.name,
            percentage=line.percentage, notes=line.notes))
        specs.append(spec)

    if unresolved:
        return RejectedFormula(
            product_name=candidate.product_name,
            reason="One or more ingredients could not be resolved to the governed "
                   "ingredient library, so their nutrition cannot be verified.",
            unresolved_ingredients=unresolved)

    # 2. Bounded mass-balance repair (proportional renormalization to 100%).
    pcts = [ln.percentage for ln in resolved]
    err = mass_balance_error(pcts)
    repaired = False
    if err > C.MASS_BALANCE_TOL:
        total = sum(pcts)
        if total <= 0 or err > _UNREPAIRABLE_ERROR:
            return RejectedFormula(
                product_name=candidate.product_name,
                reason="Ingredient percentages do not sum near 100% and cannot be "
                       "repaired without changing the intended formula.",
                violations=[Violation(
                    rule_id="mass_balance", severity="error",
                    measured=round(total, 2), limit=C.MASS_BALANCE_TARGET,
                    explanation="Sum of ingredient percentages is too far from 100%.")])
        for ln in resolved:
            ln.percentage = round(ln.percentage * 100.0 / total, 4)
        repaired = True

    # 3. Compute composition deterministically (LLM numbers never enter here).
    pairs = list(zip(specs, [ln.percentage for ln in resolved]))
    comp: ComputedComposition = compute_composition(
        pairs, candidate.product_format, candidate.overrun_pct)

    # 4. Validate (physical plausibility + active constraint modules).
    line_roles = {s.id: s.role for s in specs}
    report = validate(comp, resolved, line_roles, active_modules)
    report.repaired = repaired

    return ValidatedFormula(
        product_name=candidate.product_name,
        description=candidate.description,
        product_format=comp.product_format,
        ingredients=resolved,
        composition=comp,
        validation=report,
        formulation_notes=candidate.formulation_notes,
        verified_fields=_VERIFIED_FIELDS,
        estimated_fields=_ESTIMATED_FIELDS,
    )
