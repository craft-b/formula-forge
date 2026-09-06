"""Idea Stream — deterministic ranking over a curated trend corpus.

**This is a curated snapshot, not a live feed.** The corpus
(data/trend_ideas.json) is hand-assembled: its `social`, `momentum` and
`feasibility` values are analyst judgement on a 0-100 scale, informed by the
listed references rather than computed from them. No collection pipeline
exists. `docs/IDEA_STREAM.md` sets out what building the real thing would take.

What *is* rigorous is everything downstream of the corpus: ranking is
deterministic, driven by the corpus's own versioned weights, and the LLM has no
say in it — the same doctrine as the formulation gate. Changing weights or
signals is a data change, not a code change. Swap the hand-entered signals for
measured ones and this module needs no edit.

Score components (each 0-100):
  social      — normalized social-listening volume (given in corpus)
  momentum    — growth trajectory of the signal (given in corpus)
  breadth     — count of corroborating references, saturating at 6. Counts
                references, not verified measurements; the references carry a
                name and a note but no URL, so this is corroboration by
                assertion.
  adoption    — lifecycle position mapped through the adoption curve
                (expanding > artisan > mass > emerging: proven demand with
                remaining whitespace ranks highest)
  feasibility — how well the governed ingredient library expresses the concept
"""
from __future__ import annotations

import datetime
import json
import os
from functools import lru_cache

_DATA_PATH = os.path.join(os.path.dirname(__file__), "domain", "data", "trend_ideas.json")

_BREADTH_SATURATION = 6

# Consumer flavour trends turn over in weeks, so this corpus ages fast. These
# bounds are deliberately tight: a two-month-old snapshot is already a weak
# basis for "what is trending".
_CURRENT_MAX_DAYS = 30
_AGING_MAX_DAYS = 90


def _freshness(updated: str, today: datetime.date | None = None) -> dict:
    """How stale the corpus is, so the UI can say so rather than imply currency."""
    today = today or datetime.date.today()
    try:
        updated_on = datetime.date.fromisoformat(updated)
    except (TypeError, ValueError):
        return {"days_since_update": None, "status": "unknown",
                "note": "Corpus date is missing or unparseable."}

    days = (today - updated_on).days
    if days <= _CURRENT_MAX_DAYS:
        status, note = "current", "Curated within the last month."
    elif days <= _AGING_MAX_DAYS:
        status, note = ("aging",
                        "Over a month old. Fast-moving signals may have shifted.")
    else:
        status, note = ("stale",
                        "Over three months old. Treat rankings as historical.")
    return {"days_since_update": days, "status": status, "note": note}


@lru_cache(maxsize=1)
def _load_corpus() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _score(idea: dict, scoring: dict) -> tuple[float, dict[str, float]]:
    """Return (composite 0-100, per-component breakdown) for one idea."""
    weights = scoring["weights"]
    curve = scoring["adoption_curve"]
    sig = idea["signals"]
    lifecycle = idea["lifecycle"]
    if lifecycle not in curve:
        # This used to fall back to a neutral 50. The corpus is meant to be
        # edited — the module docstring says changing signals is a data change,
        # not a code change — so a typo is the expected way this goes wrong, and
        # a silent 50 answers it by moving the idea's adoption score without
        # telling anyone. "expanding" scores 85, so a mistyped "expandng" would
        # quietly demote an idea by 35 points and reorder the board.
        raise ValueError(
            f"idea {idea['id']!r} has lifecycle {lifecycle!r}, which is not in "
            f"the corpus adoption_curve ({sorted(curve)}). Add it to the curve "
            "or correct the idea."
        )
    components = {
        "social": float(sig["social"]),
        "momentum": float(sig["momentum"]),
        "breadth": min(len(idea["sources"]), _BREADTH_SATURATION) / _BREADTH_SATURATION * 100,
        "adoption": float(curve[lifecycle]),
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
        "freshness": _freshness(corpus["updated"]),
        "signal_basis": corpus.get("signal_basis", "analyst_judgement"),
        "methodology": corpus["methodology"],
        "scoring": scoring,
        "ideas": ideas,
    }
