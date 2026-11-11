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

The match is keyed on the nutrient, not just the number. A row's "K 150mg" does
not vouch for "150 mg of sodium": the figure is the right size and the wrong
fact, which is the harder kind of invention to notice. When the answer names the
nutrient beside the figure, the figure must match that nutrient's library value;
only a figure with no nutrient named near it falls back to matching any library
value in the same unit.

This is deliberately conservative. A figure the model derived correctly from a
library value (100 g to one cup, say) is still reported, because the library did
not supply it and the system has not checked the arithmetic.
"""
from __future__ import annotations

import re
from typing import Optional

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
_ENERGY_FAMILIES = {"kcal", "kj"}

# Nutrient identities and the words that name them. The symbols are how the
# retrieval context writes minerals ("P 90mg, K 150mg, Na 40mg"); they are
# matched case-sensitively so an ordinary "a" or "k" in prose does not count.
# Identities the library does not track (magnesium, iron, vitamins) are listed
# on purpose: a figure the answer attributes to one of them is ungrounded by
# name, rather than grounded by a coincidental library value in the same unit.
_NUTRIENT_NAMES: dict[str, tuple[str, ...]] = {
    "energy": ("energy", "calorie", "calories", "kilocalorie", "kilocalories",
               "kilojoule", "kilojoules"),
    "protein": ("protein", "proteins"),
    "fat": ("fat", "fats", "lipid", "lipids"),
    "carbs": ("carb", "carbs", "carbohydrate", "carbohydrates"),
    "sugars": ("sugar", "sugars"),
    "fiber": ("fiber", "fibre"),
    "lactose": ("lactose",),
    "phosphorus": ("phosphorus", "phosphate", "phosphates"),
    "potassium": ("potassium",),
    "sodium": ("sodium", "salt"),
    "calcium": ("calcium",),
    "magnesium": ("magnesium",),
    "iron": ("iron",),
    "zinc": ("zinc",),
    "cholesterol": ("cholesterol",),
    "vitamin": ("vitamin", "vitamins"),
}
_NUTRIENT_SYMBOLS = {"P": "phosphorus", "K": "potassium", "Na": "sodium", "Ca": "calcium"}

_NAME_RE = re.compile(
    r"\b(" + "|".join(w for ws in _NUTRIENT_NAMES.values() for w in ws) + r")\b", re.I)
_SYMBOL_RE = re.compile(r"\b(" + "|".join(_NUTRIENT_SYMBOLS) + r")\b")
_NAME_TO_IDENTITY = {w: ident for ident, ws in _NUTRIENT_NAMES.items() for w in ws}

# How far from a figure a nutrient word may sit and still be read as naming it.
# "97 mg potassium" and "potassium: 97 mg" are both within a few characters;
# forty keeps "(36 % fat): 97 mg potassium" resolving to the nearer word.
_NAME_WINDOW = 40


def _quantity(text: str) -> tuple[float, str]:
    number = _NUMBER.match(text).group(0)
    unit = text[len(number):].strip()
    for pattern, family in _UNIT_FAMILY:
        if pattern.match(unit):
            return float(number), family
    return float(number), unit.lower()


def _identity_near(text: str, start: int, end: int, family: str) -> Optional[str]:
    """The nutrient a figure at text[start:end] is attributed to, if any.

    Energy units name their own nutrient. Otherwise the nearest nutrient word
    within the window on either side wins, so a figure followed by its nutrient
    is not claimed by the previous clause's.
    """
    if family in _ENERGY_FAMILIES:
        return "energy"
    lo, hi = max(0, start - _NAME_WINDOW), min(len(text), end + _NAME_WINDOW)
    window = text[lo:hi]
    best: tuple[int, str] | None = None
    for regex, lookup in ((_NAME_RE, lambda w: _NAME_TO_IDENTITY[w.lower()]),
                          (_SYMBOL_RE, _NUTRIENT_SYMBOLS.get)):
        for m in regex.finditer(window):
            m_start, m_end = lo + m.start(), lo + m.end()
            distance = start - m_end if m_end <= start else m_start - end
            if distance < 0:
                continue  # the word sits inside the figure's own span
            if best is None or distance < best[0]:
                best = (distance, lookup(m.group(1)))
    return best[1] if best else None


def _is_basis(value: float, family: str) -> bool:
    """"per 100 g" is the basis every row is stated on, not a claim."""
    return family == "g" and value == 100


def _library_quantities(context_lines: list[str]) -> dict[tuple[Optional[str], str], list[float]]:
    """Library figures keyed by (nutrient, unit family), plus (None, family) for all.

    The ingredient name before the colon is dropped first: "Cream, heavy (36%
    fat)" would otherwise lend its "fat" to the first figure after it.
    """
    known: dict[tuple[Optional[str], str], list[float]] = {}
    for line in context_lines:
        values = line.split(":", 1)[1] if ":" in line else line
        for m in NUTRIENT_QUANTITY_RE.finditer(values):
            value, family = _quantity(m.group(0))
            if _is_basis(value, family):
                continue
            identity = _identity_near(values, m.start(), m.end(), family)
            known.setdefault((identity, family), []).append(value)
            known.setdefault((None, family), []).append(value)
    return known


def _matches(value: float, known: list[float]) -> bool:
    return any(abs(value - k) <= max(_ABS_TOL, _REL_TOL * abs(k)) for k in known)


def ungrounded_quantities(answer: str, context_lines: list[str]) -> list[str]:
    """Nutrient figures in `answer` that no retrieved library row supplies.

    Returns the matched text of each, in order of appearance, de-duplicated.
    A figure attributed to a nutrient must match that nutrient's library value;
    a figure with no nutrient named near it matches any library value in the
    same unit. Daily-value claims are always ungrounded: the library holds no
    reference intakes, so any such percentage was produced by the model.
    """
    text = answer or ""
    known = _library_quantities(context_lines)
    found: list[str] = []
    for m in NUTRIENT_QUANTITY_RE.finditer(text):
        value, family = _quantity(m.group(0))
        if _is_basis(value, family):
            continue
        identity = _identity_near(text, m.start(), m.end(), family)
        if not _matches(value, known.get((identity, family), [])):
            found.append(m.group(0).strip())
    found.extend(m.group(0).strip() for m in SERVING_CLAIM_RE.finditer(text))
    return list(dict.fromkeys(found))


def has_quantities(answer: str) -> bool:
    """Whether the answer states any nutrient figure at all."""
    return bool(NUTRIENT_QUANTITY_RE.search(answer or "")
                or SERVING_CLAIM_RE.search(answer or ""))
