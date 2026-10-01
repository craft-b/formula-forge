"""Q&A grounding check: which figures in an answer did the library supply?

The formula path cannot emit a model-authored nutrient value — the domain
recomputes every one. The Q&A path is different by construction: it streams the
model's prose, and that prose can quote the governed rows it was given or invent
a value from memory, with nothing in the text to tell the two apart. A live test
found the second case twice in three questions, each time attributed to USDA.

So every nutrient quantity in a Q&A answer is checked against the numbers in the
retrieved rows. A figure that matches one of them (within rounding) came from the
library; anything else — a nutrient the library does not track, an ingredient it
does not hold, a per-cup conversion, a daily-value percentage — is reported as
ungrounded, and the UI says so beside the answer.

This is deliberately conservative. A figure the model derived correctly from a
library value (100 g to one cup, say) is still reported, because the library did
not supply it and the system has not checked the arithmetic.
"""
from __future__ import annotations

import re

from domain.pipeline import NUTRIENT_QUANTITY_RE, SERVING_CLAIM_RE

_NUMBER = re.compile(r"\d+(?:\.\d+)?")

# The context rounds minerals to whole mg and macros to two decimals, and a model
# quoting "3.2 g" for 3.15 g is quoting, not inventing. Relative 2 % or 0.06
# absolute, whichever is looser, absorbs that and nothing a reader would call a
# different number.
_REL_TOL = 0.02
_ABS_TOL = 0.06

# Unit families. A figure is grounded only by a library number in the same unit,
# so "10 mg" of magnesium is not vouched for by a row's "10 mg" of sodium being
# nearby — and "4 IU" of vitamin D is never grounded, because no row has IU.
_UNIT_FAMILY = [
    (re.compile(r"^(?:mg|milligram)", re.I), "mg"),
    (re.compile(r"^(?:mcg|µg|μg|microgram)", re.I), "ug"),
    (re.compile(r"^(?:kg|kilogram)", re.I), "kg"),
    (re.compile(r"^(?:kcal|kilocalor|calor|cal\b)", re.I), "kcal"),
    (re.compile(r"^(?:kj|kilojoule)", re.I), "kj"),
    (re.compile(r"^(?:iu|international)", re.I), "iu"),
    (re.compile(r"^(?:g|gram)", re.I), "g"),
]


def _quantity(text: str) -> tuple[float, str]:
    number = _NUMBER.match(text).group(0)
    unit = text[len(number):].strip()
    for pattern, family in _UNIT_FAMILY:
        if pattern.match(unit):
            return float(number), family
    return float(number), unit.lower()


def _library_quantities(context_lines: list[str]) -> dict[str, list[float]]:
    known: dict[str, list[float]] = {}
    for line in context_lines:
        for m in NUTRIENT_QUANTITY_RE.finditer(line):
            value, family = _quantity(m.group(0))
            known.setdefault(family, []).append(value)
    return known


def _matches(value: float, known: list[float]) -> bool:
    return any(abs(value - k) <= max(_ABS_TOL, _REL_TOL * abs(k)) for k in known)


def ungrounded_quantities(answer: str, context_lines: list[str]) -> list[str]:
    """Nutrient figures in `answer` that no retrieved library row supplies.

    Returns the matched text of each, in order of appearance, de-duplicated.
    Daily-value claims are always ungrounded: the library holds no reference
    intakes, so any such percentage was produced by the model.
    """
    known = _library_quantities(context_lines)
    found: list[str] = []
    for m in NUTRIENT_QUANTITY_RE.finditer(answer or ""):
        value, family = _quantity(m.group(0))
        if family == "g" and value == 100:
            continue  # "per 100 g" is the basis every row is stated on, not a claim
        if not _matches(value, known.get(family, [])):
            found.append(m.group(0).strip())
    found.extend(m.group(0).strip() for m in SERVING_CLAIM_RE.finditer(answer or ""))
    return list(dict.fromkeys(found))


def has_quantities(answer: str) -> bool:
    """Whether the answer states any nutrient figure at all."""
    return bool(NUTRIENT_QUANTITY_RE.search(answer or "")
                or SERVING_CLAIM_RE.search(answer or ""))
