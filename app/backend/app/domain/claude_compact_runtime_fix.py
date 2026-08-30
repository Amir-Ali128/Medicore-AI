"""Runtime compatibility fix for compact Claude evaluation.

The compact refactor calls ``ClaudeClinicalHypothesisService._dedupe`` before
sending backend-generated flags to the model. A helper with that name was
accidentally omitted from the refactored class, causing the generate endpoint to
raise ``AttributeError`` before the Claude/fallback path could run.

This shim restores the missing helper without changing the compact evaluation
contract. It can be removed once the helper is moved into the service itself.
"""

from __future__ import annotations

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


def _dedupe(values: list[str]) -> list[str]:
    """Return values in original order with duplicates removed."""

    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


if not hasattr(ClaudeClinicalHypothesisService, "_dedupe"):
    setattr(ClaudeClinicalHypothesisService, "_dedupe", staticmethod(_dedupe))
