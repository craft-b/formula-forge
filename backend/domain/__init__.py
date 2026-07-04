"""FormulaForge domain layer — pure frozen-dessert formulation logic.

No I/O, no FastAPI, no LangGraph (the sole file-reading seam is
`repository.py`). Everything here is unit-testable in isolation. The public
entry point is `validate_candidate`: LLM proposal in, validated (or rejected)
formula out, every number computed rather than generated.
"""
from .composition import compute_composition, mass_balance_error, mass_balance_ok
from .constraints import available_modules, get_ruleset
from .models import (
    CandidateFormula,
    ComputedComposition,
    FormulaIngredient,
    RejectedFormula,
    ValidatedFormula,
    ValidationReport,
    Violation,
)
from .pipeline import validate_candidate
from .repository import get_repository

__all__ = [
    "validate_candidate",
    "compute_composition",
    "mass_balance_ok",
    "mass_balance_error",
    "available_modules",
    "get_ruleset",
    "get_repository",
    "CandidateFormula",
    "FormulaIngredient",
    "ComputedComposition",
    "ValidatedFormula",
    "RejectedFormula",
    "ValidationReport",
    "Violation",
]
