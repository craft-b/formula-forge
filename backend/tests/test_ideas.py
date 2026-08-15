"""Idea Stream ranking engine — corpus integrity and deterministic scoring."""
import datetime

import pytest

from ideas import _freshness, ranked_ideas, _load_corpus

VALID_SOURCE_TYPES = {"tiktok", "reddit", "artisan", "brand", "report"}
VALID_LIFECYCLES = {"emerging", "artisan", "expanding", "mass"}


@pytest.fixture(scope="module")
def result():
    return ranked_ideas()


def test_weights_sum_to_one():
    weights = _load_corpus()["scoring"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_scores_bounded_and_sorted_descending(result):
    scores = [i["score"] for i in result["ideas"]]
    assert all(0 <= s <= 100 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_ranks_are_contiguous_from_one(result):
    assert [i["rank"] for i in result["ideas"]] == list(range(1, len(result["ideas"]) + 1))


def test_every_idea_is_well_formed(result):
    for idea in result["ideas"]:
        assert idea["lifecycle"] in VALID_LIFECYCLES, idea["id"]
        assert idea["sources"], f"{idea['id']} has no attributed sources"
        for src in idea["sources"]:
            assert src["type"] in VALID_SOURCE_TYPES, f"{idea['id']}: {src['type']}"
        assert idea["suggested_brief"].strip(), idea["id"]
        assert set(idea["breakdown"]) == {"social", "momentum", "breadth", "adoption", "feasibility"}
        for v in idea["breakdown"].values():
            assert 0 <= v <= 100


def test_module_fits_reference_real_modules(result):
    from domain import available_modules
    known = set(available_modules())
    for idea in result["ideas"]:
        assert set(idea["module_fits"]) <= known, idea["id"]


def test_ranking_is_deterministic(result):
    again = ranked_ideas()
    assert [i["id"] for i in again["ideas"]] == [i["id"] for i in result["ideas"]]
    assert [i["score"] for i in again["ideas"]] == [i["score"] for i in result["ideas"]]


# ── Provenance and staleness ──────────────────────────────────────────────────

class TestCorpusProvenance:
    """The corpus must not imply its signals were measured."""

    def test_signal_basis_is_declared_as_judgement(self):
        payload = ranked_ideas()
        assert payload["signal_basis"] == "analyst_judgement"

    def test_methodology_does_not_claim_measurement(self):
        text = ranked_ideas()["methodology"].lower()
        assert "analyst judgement" in text
        assert "not a live feed" in text or "no collection pipeline" in text

    def test_freshness_is_reported(self):
        freshness = ranked_ideas()["freshness"]
        assert freshness["status"] in {"current", "aging", "stale", "unknown"}
        assert isinstance(freshness["note"], str) and freshness["note"]


class TestFreshness:
    @pytest.mark.parametrize("days,expected", [
        (0, "current"), (30, "current"), (31, "aging"),
        (90, "aging"), (91, "stale"), (400, "stale"),
    ])
    def test_bands(self, days, expected):
        today = datetime.date(2026, 8, 15)
        updated = (today - datetime.timedelta(days=days)).isoformat()
        assert _freshness(updated, today)["status"] == expected

    def test_unparseable_date_does_not_raise(self):
        result = _freshness("not-a-date", datetime.date(2026, 8, 15))
        assert result["status"] == "unknown"
        assert result["days_since_update"] is None

    def test_days_are_reported(self):
        today = datetime.date(2026, 8, 15)
        assert _freshness("2026-07-13", today)["days_since_update"] == 33
