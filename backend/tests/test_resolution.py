"""Reference resolution: the seam where model text becomes a nutrient vector.

Nothing covered this, and two defects were living in it.

`resolve` scored candidates and kept the first one at the best score, so when
several tied the winner was decided by dict insertion order — the order of rows
in ingredients.json. "milk" tied three ways across whole, skim and 2%, whose fat
content differs by a factor of forty. "milk powder" scored exactly 0.5 against
liquid whole milk (88% water) and could never reach nonfat dry milk (3% water),
because the head-token guard requires the ingredient's first name token and dry
milk's is "nonfat".

Either way the caller received a complete, confident composition computed from an
ingredient nobody chose. The module's own contract is that an unresolvable
reference is reported rather than guessed; an ambiguous one is now treated the
same way, which sends the offending name back to the model in the repair prompt.
"""
from __future__ import annotations

import pytest

from domain.repository import IngredientRepository, get_repository


@pytest.fixture(scope="module")
def repo():
    return get_repository()


class TestExactMatches:
    def test_resolves_by_id(self, repo):
        assert repo.resolve("milk_whole").id == "milk_whole"

    def test_resolves_by_exact_name(self, repo):
        assert repo.resolve("Milk, whole, 3.25% fat").id == "milk_whole"

    def test_exact_name_is_case_insensitive(self, repo):
        assert repo.resolve("MILK, WHOLE, 3.25% FAT").id == "milk_whole"


class TestSpecificReferencesStillResolve:
    """The fix must not cost the matches the pipeline depends on."""

    @pytest.mark.parametrize("ref,expected", [
        ("milk whole", "milk_whole"),
        ("cream heavy", "cream_heavy"),
        ("nonfat dry milk", "nonfat_dry_milk"),
        ("cocoa powder", "cocoa_powder"),
        ("guar gum", "guar_gum"),
        ("vanilla extract", "vanilla_extract"),
        ("sucrose", "sucrose"),
    ])
    def test_resolves(self, repo, ref, expected):
        got = repo.resolve(ref)
        assert got is not None, f"{ref!r} no longer resolves"
        assert got.id == expected


class TestAmbiguousReferencesAreRefused:
    @pytest.mark.parametrize("ref", ["milk", "cream"])
    def test_bare_family_name_does_not_resolve(self, repo, ref):
        # Several library entries share this head token. Picking one silently
        # attaches a nutrient vector the caller never asked for.
        assert repo.resolve(ref) is None

    def test_milk_powder_does_not_resolve_to_liquid_milk(self, repo):
        """The specific mis-resolution: 88% water where 3% was meant."""
        assert repo.resolve("milk powder") is None

    def test_unknown_reference_is_unresolved(self, repo):
        assert repo.resolve("unobtainium") is None

    def test_generic_token_alone_cannot_match(self, repo):
        # "powder" is shared by several names; on its own it must not resolve.
        assert repo.resolve("powder") is None


class TestResolutionDoesNotDependOnDatasetOrder:
    """Order of rows in ingredients.json must not change any answer.

    This is the property the old tie-break violated: reordering the file, which
    the ETL is free to do, could have changed which milk a formula was built
    from without a single line of code changing.
    """

    @pytest.mark.parametrize("ref", [
        "milk", "cream", "milk powder", "milk whole", "cream heavy",
        "nonfat dry milk", "sucrose", "unobtainium",
    ])
    def test_same_answer_when_the_library_is_reversed(self, repo, ref):
        reversed_repo = IngredientRepository(
            list(reversed(repo.ingredients)), version=repo.version)
        forward = repo.resolve(ref)
        backward = reversed_repo.resolve(ref)
        assert (forward is None) == (backward is None)
        if forward is not None:
            assert forward.id == backward.id
