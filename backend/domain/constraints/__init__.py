"""Declarative dietary-constraint modules.

Each module is a versioned JSON ruleset in `rulesets/`. Adding a module (e.g.
low-FODMAP) means adding a ruleset file — no core code changes (open/closed).
The evaluator is generic: it reads limits and blacklists from the ruleset and
checks them against the deterministic `ComputedComposition` and resolved lines.
Constraint logic lives here as data, never in LLM prompt text.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from ..models import ComputedComposition, ResolvedLine, Violation

_RULESET_DIR = os.path.join(os.path.dirname(__file__), "rulesets")


@lru_cache(maxsize=1)
def _load_all() -> dict[str, dict]:
    modules: dict[str, dict] = {}
    for fname in os.listdir(_RULESET_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(_RULESET_DIR, fname), encoding="utf-8") as f:
            rs = json.load(f)
        modules[rs["module_id"]] = rs
    return modules


def available_modules() -> list[str]:
    return sorted(_load_all().keys())


def get_ruleset(module_id: str) -> dict | None:
    return _load_all().get(module_id)


def _measured(comp: ComputedComposition, field: str, basis: str) -> float:
    vec = comp.nutrients_per_serving if basis == "per_serving" else comp.nutrients_per_100g
    return getattr(vec, field)


def evaluate_module(
    module_id: str,
    comp: ComputedComposition,
    lines: list[ResolvedLine],
    line_specs: dict[str, str],  # ingredient_id -> role
) -> list[Violation]:
    """Return violations for one constraint module against a computed formula."""
    rs = get_ruleset(module_id)
    if rs is None:
        return [Violation(rule_id=f"{module_id}.unknown", severity="error",
                          explanation=f"Unknown constraint module '{module_id}'.")]

    # Stub modules (e.g. dysphagia_iddsi) advise but never fail.
    if rs.get("stub"):
        return [Violation(
            rule_id=f"{module_id}.stub", severity="warn",
            explanation=f"{rs['label']}: texture evaluation is not yet implemented; "
                        "requires professional review.")]

    violations: list[Violation] = []

    for limit in rs.get("nutrient_limits", []):
        val = _measured(comp, limit["field"], limit.get("basis", "per_serving"))
        if "max" in limit and val > limit["max"] + 1e-6:
            violations.append(Violation(
                rule_id=limit["rule_id"], severity="error",
                measured=round(val, 2), limit=limit["max"],
                explanation=limit["explanation"]))
        if "min" in limit and val < limit["min"] - 1e-6:
            violations.append(Violation(
                rule_id=limit["rule_id"], severity="error",
                measured=round(val, 2), limit=limit["min"],
                explanation=limit["explanation"]))

    black_roles = set(rs.get("ingredient_blacklist_roles", []))
    black_ids = set(rs.get("ingredient_blacklist_ids", []))
    for line in lines:
        role = line_specs.get(line.ingredient_id, "")
        if line.ingredient_id in black_ids or role in black_roles:
            violations.append(Violation(
                rule_id=f"{module_id}.blacklist", severity="error",
                explanation=f"Ingredient '{line.ingredient_name}' is not permitted "
                            f"under the {rs['label']} module."))

    black_allergens = set(rs.get("allergen_blacklist", []))
    present = set(comp.allergens) & black_allergens
    for allergen in sorted(present):
        violations.append(Violation(
            rule_id=f"{module_id}.allergen.{allergen}", severity="error",
            explanation=f"Allergen '{allergen}' is not permitted under the "
                        f"{rs['label']} module."))

    return violations
