"""Compatibility refinements for performed-study canonicalization."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.domain import clinical_rule_extensions_runtime as rules

_original_canonical_study_codes = rules._canonical_study_codes
_original_performed_studies = rules._performed_studies


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


def _date_key(value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return date.fromisoformat(text).toordinal()
    except ValueError:
        return 0


def _performed_studies_with_inventory(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for item in _original_performed_studies(metadata):
        code = str(item.get("code") or "").strip().upper()
        if code:
            merged[code] = {
                "code": code,
                "name": str(item.get("name") or code),
                "date": item.get("date"),
            }

    explicit = metadata.get("performed_studies")
    if isinstance(explicit, list):
        for item in explicit[:50]:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip().upper()
            # Only canonical machine codes survive this boundary. Filenames,
            # report text and direct identifiers are deliberately ignored.
            if not code or not code.replace("_", "").isalnum():
                continue
            candidate = {
                "code": code,
                "name": str(item.get("name") or code)[:120],
                "date": str(item.get("date") or "")[:10] or None,
            }
            existing = merged.get(code)
            if existing is None or _date_key(candidate.get("date")) >= _date_key(existing.get("date")):
                merged[code] = candidate

    return [merged[key] for key in sorted(merged)]


rules._canonical_study_codes = _canonical_study_codes_with_abdominal_context
rules._performed_studies = _performed_studies_with_inventory
