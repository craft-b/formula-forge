"""The single path from an LLM proposal to a user-facing formula.

`validate_candidate` is the ONLY function the API layer calls to turn a
`CandidateFormula` (LLM structure proposal) into something a user may see. It
resolves ingredients against the governed library, discards any LLM-supplied
numbers (there are none in the model by construction), computes the composition
deterministically, runs a bounded mass-balance repair, and validates. There is
no other route from generation to the client — enforced by an integration test.
"""
from __future__ import annotations

import re

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

# Provenance surfaced to the UI. The distinction is about where a number's
# authority comes from, not how hard it was to compute.
#
# Verified: derived by mass balance from the governed ingredient library. Given
# the same ingredients and percentages, these are reproducible by hand.
_VERIFIED_FIELDS = [
    "nutrients_per_100g", "nutrients_per_serving", "total_solids_pct", "fat_pct",
    "msnf_pct", "sugars_pct", "lactose_pct", "pac_total", "pod_total",
    "serving_g", "total_cost_per_kg_usd", "allergens",
]

# Estimated: computed deterministically, but from an empirical relationship
# rather than mass balance, so it carries model error of its own.
_ESTIMATED_FIELDS = ["scoopability_index"]

# Depends on the process assumption (overrun) as well as the formula. Overrun
# comes from the user's product format or an explicit caller value — never from
# the LLM — but a reader comparing two formulas should know that changing the
# format moves these without any ingredient changing.
_PROCESS_DEPENDENT_FIELDS = ["serving_g", "nutrients_per_serving", "overrun_pct"]

_UNREPAIRABLE_ERROR = 40.0  # percentage points off 100 beyond which we reject

# A nutrition quantity inside model-authored prose — the one kind of number
# here that can contradict what the rules computed.
#
# This was previously any digit followed by a letter, which the live eval scored
# at 0/37: it fired on every formula, because the prompt asks notes to cover
# processing and processing is written in numbers. "Age the mix for 4 hours at
# 4C" tripped it exactly as hard as "roughly 200 mg calcium per serving". A flag
# that never varies carries no information, and a UI warning attached to every
# single formula is one readers learn to skip — so the broad version was worse
# than useless, not merely noisy.
#
# The narrow question is whether prose asserts a NUTRIENT value, since that is
# what sits beside rule-computed values looking identical. Time, temperature,
# speed and dimensions cannot be confused for nutrition, so they are not
# flagged. Percentages stay excluded: the model is discussing its own ingredient
# percentages, which the domain has already verified.
_NUTRIENT_UNIT = r"""(?:
      k?cal | (?:kilo)?calories? | kj | kilojoules?
    | (?:milli|micro|kilo)?gram(?:me)?s? | mg | mcg | µg | kg | g
    | IU | international\s+units?
)"""

#: A quantity in a unit the domain itself computes.
_NUTRIENT_QUANTITY = re.compile(
    rf"\b\d+(?:\.\d+)?\s*{_NUTRIENT_UNIT}\b",
    re.IGNORECASE | re.VERBOSE,
)

#: A serving-level or daily-value assertion, which is a nutrition claim even
#: when the unit is a percent — "supplies 20% of the daily value for calcium".
_SERVING_CLAIM = re.compile(
    r"\b\d+(?:\.\d+)?\s*%?\s*(?:of\s+)?"
    r"(?:the\s+)?(?:recommended|daily)\s*(?:value|intake|allowance)"
    r"|\b\d+(?:\.\d+)?\s*%\s*DV\b",
    re.IGNORECASE,
)

_NUMERIC_CLAIM = _NUTRIENT_QUANTITY  # kept for callers that import the name


def _has_numeric_claim(*texts: str) -> bool:
    """Whether model-authored prose asserts a quantity.

    Model prose is the one surface the domain cannot verify. It is shown
    because it is useful, but the UI needs to know when it contains numbers so
    it can say they are unverified rather than letting them sit beside
    rule-computed values looking identical.
    """
    return any(
        _NUTRIENT_QUANTITY.search(text or "") or _SERVING_CLAIM.search(text or "")
        for text in texts
    )


def validate_candidate(
    candidate: CandidateFormula,
    active_modules: list[str] | None = None,
    repo: IngredientRepository | None = None,
    overrun_pct: float | None = None,
) -> ValidatedFormula | RejectedFormula:
    """Turn an LLM structure proposal into something a user may see.

    Args:
        candidate: The model's proposal. Structure only — no nutrition, and
            no overrun.
        active_modules: Clinical rulesets to enforce.
        repo: Ingredient library. Defaults to the governed one.
        overrun_pct: Overrun supplied by the *caller* on the user's behalf.
            None derives it from `candidate.product_format`. This parameter
            exists so overrun stays user-controlled; nothing on the candidate
            can reach it.
    """
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
        pairs, candidate.product_format, overrun_pct)

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
        process_dependent_fields=_PROCESS_DEPENDENT_FIELDS,
        notes_contain_numeric_claims=_has_numeric_claim(
            candidate.formulation_notes,
            *(ln.notes for ln in resolved),
        ),
        estimated_fields=_ESTIMATED_FIELDS,
    )
