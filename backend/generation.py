"""LLM proposal → validated formula. The one adapter, shared by every caller.

This is the seam between generated structure and verified output. It lived
inside `main.py` until the live eval needed it: an eval that reimplements the
parsing and validation path measures a pipeline that is not the one serving
users, and would drift away from it silently. The same reasoning retired the
two divergent JSON fence-strippers (audit finding F13).

Importing `main` from the eval was the alternative and is worse — it builds the
FastAPI app, the rate limiter, the CORS allowlist and the token budget as an
import side effect, none of which an offline scorer should touch.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from domain import CandidateFormula, RejectedFormula, ValidatedFormula, validate_candidate
from json_utils import extract_json_block

logger = logging.getLogger(__name__)


def candidate_from_llm(raw: dict) -> CandidateFormula:
    """Adapt a raw LLM formula dict to a CandidateFormula (structure only).

    Any nutrition the LLM supplied is intentionally ignored — the domain layer
    computes all nutrition from the governed ingredient library. `overrun_pct`
    is dropped for the same reason: it divides every per-serving value, so
    letting the model set it would hand it control of the numbers the clinical
    rulesets are checked against.
    """
    ingredients = []
    for item in raw.get("ingredients", []):
        ingredients.append({
            "ref": item.get("ref") or item.get("name") or "",
            "percentage": item.get("percentage", 0),
            "notes": item.get("notes", ""),
        })
    return CandidateFormula(
        product_name=raw.get("product_name") or "Formula",
        description=raw.get("description", ""),
        product_format=raw.get("product_format") or "standard",
        ingredients=ingredients,
        formulation_notes=raw.get("formulation_notes", ""),
    )


def parse_and_validate(
    raw_text: str,
    active_modules: Optional[list],
    product_format: Optional[str] = None,
) -> ValidatedFormula | RejectedFormula | None:
    """Parse raw LLM text and run it through the domain gate. None on parse failure.

    An explicit `product_format` (user's brief-builder selection) overrides the
    LLM's guess — serving/overrun math then reflects what the user chose.
    """
    try:
        raw = json.loads(extract_json_block(raw_text))
        candidate = candidate_from_llm(raw)
        if product_format:
            candidate.product_format = product_format
        return validate_candidate(candidate, active_modules=active_modules or [])
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Formula parse/validation setup failed: %s", exc)
        return None
