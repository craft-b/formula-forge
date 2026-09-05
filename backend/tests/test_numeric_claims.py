"""The numeric-claim flag: what counts as a claim the domain did not compute.

Model prose is the one surface the domain cannot verify, so the UI marks it when
it asserts a quantity. The question is which quantities matter.

The first version flagged any digit followed by a letter and scored 0/37 on a
live run — it fired on every formula, because the prompt asks notes to cover
processing and processing is written in numbers. A warning attached to every
single formula carries no information and readers learn to skip it, which made
the broad version worse than useless rather than merely noisy.

A nutrient value is the thing that can sit beside a rule-computed value looking
identical and contradict it. A pasteurisation temperature cannot. That is the
line these tests hold, in both directions: the false positives that emptied the
flag of meaning, and the true positives that are the reason it exists.
"""
from __future__ import annotations

import pytest

from domain.pipeline import _has_numeric_claim


class TestProcessParametersAreNotClaims:
    """Every one of these is what the prompt explicitly asks notes to contain."""

    @pytest.mark.parametrize("note", [
        "Age the mix for 4 hours at 4C before freezing.",
        "Pasteurize at 82C for 25 seconds.",
        "Draw at -6C; harden at -18C overnight.",
        "Homogenize at 2000 psi in two stages.",
        "Agitate at 500 rpm for 3 minutes.",
        "Use a 40 mesh screen.",
        "Hold at 4 degrees for 12 hours.",
        "Rest 24 h, then draw.",
        "Age 12 hr minimum.",
        "Cool to 4 C within 90 min.",
    ])
    def test_time_temperature_and_equipment_settings(self, note):
        assert not _has_numeric_claim(note), f"process parameter flagged: {note}"

    def test_the_models_own_percentages_are_not_claims(self):
        """The domain has already verified the composition it is describing."""
        assert not _has_numeric_claim("Coconut cream at 30% carries the fat phase.")
        assert not _has_numeric_claim("Target overrun is 100%.")

    def test_prose_without_numbers_is_not_a_claim(self):
        assert not _has_numeric_claim("Blend the gums with the sugars before hydrating.")

    def test_empty_and_missing_text_is_safe(self):
        assert not _has_numeric_claim("")
        assert not _has_numeric_claim(None)  # type: ignore[arg-type]
        assert not _has_numeric_claim()


class TestNutrientQuantitiesAreClaims:
    """The reason the flag exists: a number the rules did not produce."""

    @pytest.mark.parametrize("note", [
        "Provides roughly 200 mg calcium per serving.",
        "Delivers 12 g of protein.",
        "Approximately 150 kcal per portion.",
        "Contains 3 grams of fat.",
        "About 250 IU vitamin D.",
        "Each serving has 5 g fibre.",
        "180 kJ per serving.",
        "Around 0.5 kg of mix yields 12 servings.",
        "Supplies 800 mcg folate.",
        "Roughly 2.5 g saturated fat.",
    ])
    def test_a_quantity_in_a_unit_the_domain_computes(self, note):
        assert _has_numeric_claim(note), f"nutrient claim missed: {note}"

    @pytest.mark.parametrize("note", [
        "Supplies 20% of the daily value for potassium.",
        "Provides 15% DV calcium.",
        "Covers 30% of the recommended intake.",
    ])
    def test_daily_value_claims_count_despite_the_percent(self, note):
        """Percent is otherwise excluded, but a daily-value figure is a
        nutrition assertion regardless of the unit it wears."""
        assert _has_numeric_claim(note), f"daily-value claim missed: {note}"


class TestAcrossMultipleFields:
    def test_any_field_carrying_a_claim_flags_the_whole_formula(self):
        assert _has_numeric_claim(
            "Blend gently.", "Age 4 hours.", "Provides 200 mg calcium.")

    def test_all_clean_fields_stay_clean(self):
        assert not _has_numeric_claim(
            "Blend gently.", "Age 4 hours at 4C.", "Draw at -6C.")


class TestTheRegressionThisReplaces:
    """Named for the finding, so reverting to the broad pattern fails by name.

    F-E5 in docs/EVAL_FINDINGS.md: prose_free_of_numeric_claims scored 0/37
    because processing notes tripped the detector.
    """

    def test_a_typical_processing_note_no_longer_fires(self):
        note = ("Pasteurize at 82C for 25 seconds, homogenize, age 4 hours at "
                "4C, then draw at -6C and harden overnight at -18C.")
        assert not _has_numeric_claim(note)

    def test_a_note_mixing_process_and_nutrition_still_fires(self):
        """Narrowing must not create a hiding place: a real claim buried in
        legitimate processing prose is exactly the case that matters."""
        note = ("Pasteurize at 82C for 25 seconds, age 4 hours at 4C. "
                "Provides roughly 200 mg calcium per serving.")
        assert _has_numeric_claim(note)
