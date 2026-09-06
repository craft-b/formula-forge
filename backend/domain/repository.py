"""Ingredient library access — the domain's single I/O seam.

Everything else in `domain/` is pure and receives already-resolved
`IngredientSpec` objects. This module loads the governed dataset built by the
ETL (`domain/data/ingredients.json`) and resolves LLM ingredient references
(free-text names or ids) to library entries.

Resolution is deliberately conservative: an exact id or name match, then a
token-overlap match. An unresolved reference is NOT guessed — it is reported so
the validator can hard-fail it (spec §4.3: no phantom ingredients).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from .models import IngredientSpec

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "ingredients.json")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Generic tokens that must not, on their own, carry a match.
_STOPWORDS = frozenset({
    "the", "and", "with", "for", "of", "a", "an", "raw", "fat", "low",
    "full", "fresh", "plain", "added", "reduced", "unsweetened",
})


def _token_list(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower())
            if len(t) > 2 and t not in _STOPWORDS]


def _tokens(text: str) -> set[str]:
    return set(_token_list(text))


class IngredientRepository:
    def __init__(self, ingredients: list[IngredientSpec], version: str = ""):
        self._by_id = {ing.id: ing for ing in ingredients}
        self._by_name = {ing.name.lower(): ing for ing in ingredients}
        self._token_index = {ing.id: _tokens(f"{ing.name} {ing.id}")
                             for ing in ingredients}
        # Primary (head) token of each ingredient name, e.g. "cocoa" for
        # "Cocoa powder". A fuzzy match must include this token, so a generic
        # shared word like "powder" alone cannot resolve a phantom ingredient.
        self._primary = {}
        for ing in ingredients:
            toks = _token_list(ing.name) or _token_list(ing.id)
            self._primary[ing.id] = toks[0] if toks else ing.id
        self.version = version

    @property
    def ingredients(self) -> list[IngredientSpec]:
        return list(self._by_id.values())

    def get(self, ingredient_id: str) -> IngredientSpec | None:
        return self._by_id.get(ingredient_id)

    def resolve(self, ref: str) -> IngredientSpec | None:
        """Resolve a free-text ref to a library ingredient, or None."""
        key = ref.strip().lower()
        if ref in self._by_id:
            return self._by_id[ref]
        if key in self._by_name:
            return self._by_name[key]

        ref_tokens = _tokens(ref)
        if not ref_tokens:
            return None
        scored: list[tuple[float, str]] = []
        for ing_id, idx_tokens in self._token_index.items():
            # Guard against phantom matches: the ingredient's head token must be
            # present in the reference (a shared generic word is not enough).
            if self._primary[ing_id] not in ref_tokens:
                continue
            overlap = ref_tokens & idx_tokens
            if not overlap:
                continue
            scored.append((len(overlap) / len(ref_tokens), ing_id))

        # Require at least half the ref's meaningful tokens to match.
        best_score = max((s for s, _ in scored), default=0.0)
        if best_score < 0.5:
            return None

        # An ambiguous reference is an unresolved one. Previously the first
        # ingredient at the best score won, which meant dict insertion order --
        # i.e. the order of rows in ingredients.json -- silently decided the
        # answer. "milk" tied three ways across whole, skim and 2%, whose fat
        # differs by a factor of forty, and "milk powder" landed on liquid whole
        # milk at exactly the 0.5 threshold: 88% water where nonfat dry milk is
        # 3%. Both produced a complete, confident nutrient vector for an
        # ingredient nobody chose.
        #
        # Refusing instead is what this module already claims to do -- a
        # reference that cannot be pinned down is reported, not guessed -- and
        # the caller hard-fails it, which puts the ingredient name in front of
        # the model in the repair prompt.
        tied = [ing_id for score, ing_id in scored if score == best_score]
        if len(tied) > 1:
            return None
        return self._by_id[tied[0]]


@lru_cache(maxsize=1)
def get_repository() -> IngredientRepository:
    with open(_DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    ingredients = [IngredientSpec.model_validate(row) for row in raw["ingredients"]]
    return IngredientRepository(ingredients, version=raw.get("dataset_version", ""))
