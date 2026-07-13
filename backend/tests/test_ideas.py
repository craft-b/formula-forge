"""Idea Stream ranking engine — corpus integrity and deterministic scoring."""
import pytest

from ideas import ranked_ideas, _load_corpus

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
