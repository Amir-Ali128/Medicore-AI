"""Small compatibility refinement for performed-study canonicalization."""

from __future__ import annotations

from app.domain import clinical_rule_extensions_runtime as rules

_original_canonical_study_codes = rules._canonical_study_codes


def _canonical_study_codes_with_abdominal_context(text: object) -> set[str]:
    codes = set(_original_canonical_study_codes(text))
    folded = rules._fold(text)
    # This function is only called for the ultrasound source summary. A result
    # section may omit the word "ultrasound" even though it clearly describes
    # abdominal organs. Treat those organ terms as canonical abdominal-US evidence.
    if any(
        token in folded
        for token in (
            "karaciger",
            "hepatomegali",
            "portal ven",
            "mezenterik ven",
            "dalak",
            "splenomegali",
            "pankreas",
            "safra",
            "abdomen",
        )
    ):
        codes.add("US_ABDOMEN")
    return codes


rules._canonical_study_codes = _canonical_study_codes_with_abdominal_context
