"""Idea Stream — deterministic ranking over the governed trend corpus.

The corpus (data/trend_ideas.json) is curated consumer-trend intelligence with
attributed sources. This module computes each idea's score from the corpus's
own versioned weights — the same doctrine as the formulation gate: the LLM has
no say in the ranking, and changing weights or signals is a data change, not a
code change.

Score components (each 0-100):
  social      — normalized social-listening volume (given in corpus)
  momentum    — growth trajectory of the signal (given in corpus)
  breadth     — distinct attributed sources, saturating at 6
  adoption    — lifecycle position mapped through the adoption curve
                (expanding > artisan > mass > emerging: proven demand with
                remaining whitespace ranks highest)
  feasibility — how well the governed ingredient library expresses the concept
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

_DATA_PATH = os.path.join(os.path.dirname(__file__), "domain", "data", "trend_ideas.json")

_BREADTH_SATURATION = 6


@lru_cache(maxsize=1)
def _load_corpus() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _score(idea: dict, scoring: dict) -> tuple[float, dict[str, float]]:
    """Return (composite 0-100, per-component breakdown) for one idea."""
    weights = scoring["weights"]
    curve = scoring["adoption_curve"]
    sig = idea["signals"]
    components = {
        "social": float(sig["social"]),
        "momentum": float(sig["momentum"]),
        "breadth": min(len(idea["sources"]), _BREADTH_SATURATION) / _BREADTH_SATURATION * 100,
        "adoption": float(curve.get(idea["lifecycle"], 50)),
        "feasibility": float(sig["feasibility"]),
    }
    composite = sum(weights[k] * components[k] for k in weights)
    return round(composite, 1), {k: round(v, 1) for k, v in components.items()}


def ranked_ideas() -> dict:
    """The corpus with computed scores, ranked descending. Deterministic."""
    corpus = _load_corpus()
    scoring = corpus["scoring"]
    ideas = []
    for idea in corpus["ideas"]:
        score, breakdown = _score(idea, scoring)
        ideas.append({**idea, "score": score, "breakdown": breakdown})
    ideas.sort(key=lambda i: (-i["score"], i["id"]))
    for rank, idea in enumerate(ideas, start=1):
        idea["rank"] = rank
    return {
        "dataset_version": corpus["dataset_version"],
        "updated": corpus["updated"],
        "methodology": corpus["methodology"],
        "scoring": scoring,
        "ideas": ideas,
    }
