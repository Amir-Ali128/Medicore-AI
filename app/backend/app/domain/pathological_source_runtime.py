"""Attach raw source value, date and deterministic trend deltas to UI findings."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis


def _fold(value: object) -> str:
    text = str(value or "")
    translated = text.translate(
        str.maketrans(
            {
                "ı": "i",
                "İ": "i",
                "ş": "s",
                "Ş": "s",
                "ğ": "g",
                "Ğ": "g",
                "ü": "u",
                "Ü": "u",
                "ö": "o",
                "Ö": "o",
                "ç": "c",
                "Ç": "c",
            }
        )
    )
    normalized = unicodedata.normalize("NFKD", translated)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).strip().lower()


def _build_hypothesis_with_source_fidelity(
    self: ClaudeClinicalHypothesisService,
    run: Any,
    *,
    risk: int,
    summary: str,
    flags: list[str],
    symptoms: list[str],
    evidence: list[dict[str, Any]],
    ai_called: bool,
):
    hypothesis = _original_build_hypothesis(
        self,
        run,
        risk=risk,
        summary=summary,
        flags=flags,
        symptoms=symptoms,
        evidence=evidence,
        ai_called=ai_called,
    )
    metadata = dict(hypothesis.metadata_json or {})
    findings = list(metadata.get("pathological_findings") or [])

    evidence_by_name: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, dict):
            continue
        for candidate in (item.get("parameter_name"), item.get("parameter_code")):
            key = _fold(candidate)
            if key:
                evidence_by_name.setdefault(key, item)

    for finding in findings:
        if not isinstance(finding, dict) or finding.get("source") != "laboratory":
            continue
        item = evidence_by_name.get(_fold(finding.get("name")))
        if item is None:
            continue
        raw_value = item.get("raw_value")
        finding["raw_value"] = raw_value
        finding["measured_at"] = item.get("measured_at")
        finding["previous_value"] = item.get("previous_value")
        finding["absolute_difference"] = item.get("absolute_difference")
        finding["percentage_difference"] = item.get("percentage_difference")
        finding["time_difference_days"] = item.get("time_difference_days")
        finding["trend_status"] = item.get("trend_status")
        if isinstance(raw_value, str) and (
            "+" in raw_value
            or raw_value.strip().casefold()
            in {"negatif", "negative", "pozitif", "positive", "normal", "eser", "trace"}
        ):
            finding["display_value"] = raw_value
        else:
            finding["display_value"] = finding.get("value")

    metadata["pathological_findings"] = findings
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_source_fidelity
