"""The validation gate (pure).

Given a computed composition and the active constraint modules, produce a
`ValidationReport`. `passed` is True only when there are zero error-severity
violations. Physical-plausibility excursions are quality advisories (warn);
gross impossibilities and constraint-module breaches are errors.

This function is the gate referenced by the prime directive: no formula reaches
a user without a report from here, and nothing constructs user-facing numbers
except `composition.py`.
"""
from __future__ import annotations

from . import constants as C
from .constraints import evaluate_module
from .models import ComputedComposition, ResolvedLine, ValidationReport, Violation


def _band_warn(rule_id: str, value: float, band: tuple[float, float], what: str) -> list[Violation]:
    lo, hi = band
    if value < lo:
        return [Violation(rule_id=rule_id, severity="warn", measured=round(value, 2),
                          limit=lo, explanation=f"{what} below the typical band ({lo}–{hi}).")]
    if value > hi:
        return [Violation(rule_id=rule_id, severity="warn", measured=round(value, 2),
                          limit=hi, explanation=f"{what} above the typical band ({lo}–{hi}).")]
    return []


def _physical_violations(comp: ComputedComposition) -> list[Violation]:
    v: list[Violation] = []

    # Gross total-solids impossibility = error (not a frozen dessert at all).
    ts = comp.total_solids_pct
    if ts < 20.0 or ts > 60.0:
        v.append(Violation(
            rule_id="physical.total_solids", severity="error",
            measured=round(ts, 2), limit=None,
            explanation="Total solids are outside any frozen-dessert range "
                        "(20–60%); this composition cannot be a frozen dessert."))
    else:
        v += _band_warn("physical.total_solids", ts, C.TOTAL_SOLIDS_BAND, "Total solids")

    v += _band_warn("physical.fat", comp.fat_pct, C.FAT_BAND, "Fat")
    v += _band_warn("physical.msnf", comp.msnf_pct, C.MSNF_BAND, "MSNF")
    v += _band_warn("physical.pac", comp.pac_total, C.PAC_BAND,
                    "PAC (freezing-point depression)")
    v += _band_warn("physical.pod", comp.pod_total, C.POD_BAND, "POD (sweetness)")
    v += _band_warn("physical.stabilizer", comp.stabilizer_pct, C.STABILIZER_BAND,
                    "Stabilizer/emulsifier total")

    if comp.lactose_pct > C.LACTOSE_SANDINESS_CEILING:
        v.append(Violation(
            rule_id="physical.lactose_sandiness", severity="warn",
            measured=round(comp.lactose_pct, 2), limit=C.LACTOSE_SANDINESS_CEILING,
            explanation="Lactose exceeds the sandiness ceiling; risk of gritty "
                        "texture from lactose crystallization."))
    return v


def validate(
    comp: ComputedComposition,
    lines: list[ResolvedLine],
    line_roles: dict[str, str],
    active_modules: list[str],
) -> ValidationReport:
    violations = _physical_violations(comp)
    for module_id in active_modules:
        violations += evaluate_module(module_id, comp, lines, line_roles)
    passed = not any(v.severity == "error" for v in violations)
    return ValidationReport(passed=passed, violations=violations,
                            active_modules=list(active_modules))
