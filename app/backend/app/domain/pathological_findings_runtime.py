"""Expose deterministic pathological findings without increasing LLM context.

The compact AI service already filters normal lab results before building evidence.
This runtime extension converts only deterministic HIGH/LOW evidence into a small,
structured ``pathological_findings`` list for the physician UI. The list is never
added to the LLM prompt; Claude still receives only symptoms + backend flags.
"""

from __future__ import annotations

from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis

_VITAL_FLAG_LABELS: dict[str, tuple[str, str]] = {
    "BLOOD_PRESSURE_HIGH": ("Kan basıncı", "yüksek"),
    "BLOOD_PRESSURE_LOW": ("Kan basıncı", "düşük"),
    "BLOOD_PRESSURE_CRITICAL_REVIEW": ("Kan basıncı", "kritik değerlendirme"),
    "PULSE_HIGH": ("Nabız", "yüksek"),
    "PULSE_LOW": ("Nabız", "düşük"),
    "TEMPERATURE_HIGH": ("Vücut sıcaklığı", "yüksek"),
    "TEMPERATURE_LOW": ("Vücut sıcaklığı", "düşük"),
    "RESPIRATORY_RATE_HIGH": ("Solunum sayısı", "yüksek"),
    "RESPIRATORY_RATE_LOW": ("Solunum sayısı", "düşük"),
    "OXYGEN_SATURATION_LOW": ("Oksijen satürasyonu", "düşük"),
    "OXYGEN_SATURATION_CRITICAL_REVIEW": (
        "Oksijen satürasyonu",
        "kritik değerlendirme",
    ),
}


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def _pathological_findings(
    evidence: list[dict[str, Any]], flags: list[str]
) -> list[dict[str, Any]]:
    """Return only deterministically abnormal findings.

    UNKNOWN/NEEDS_REVIEW values are deliberately not labelled pathological: an
    unmapped or uncertain parameter is a data-quality/review issue, not proof of
    abnormality.
    """

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in evidence:
        status = str(item.get("result_status") or "").lower()
        if status not in {"high", "low"}:
            continue

        name = _clean(item.get("parameter_name")) or _clean(item.get("parameter_code"))
        if not name:
            name = "Laboratuvar parametresi"
        value = _clean(item.get("value"))
        unit = _clean(item.get("unit"))
        direction = "yüksek" if status == "high" else "düşük"
        key = (name.casefold(), status)
        if key in seen:
            continue
        seen.add(key)

        value_text = " ".join(part for part in (value, unit) if part) or None
        findings.append(
            {
                "source": "laboratory",
                "name": name,
                "status": status,
                "status_label": direction,
                "value": value,
                "unit": unit,
                "display": f"{name}: {value_text} ({direction})"
                if value_text
                else f"{name}: {direction}",
            }
        )

    # Vital signs are converted to backend flags before the LLM call. Surface the
    # flag meaning to the physician UI without sending raw vital values to Claude.
    for flag in flags:
        mapped = _VITAL_FLAG_LABELS.get(flag)
        if mapped is None:
            continue
        name, label = mapped
        key = (name.casefold(), flag)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "source": "vital",
                "name": name,
                "status": flag.lower(),
                "status_label": label,
                "value": None,
                "unit": None,
                "display": f"{name}: {label}",
            }
        )

    return findings[:20]


def _build_hypothesis_with_pathological_findings(
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
    findings = _pathological_findings(evidence, flags)
    metadata = dict(hypothesis.metadata_json or {})
    metadata["pathological_findings"] = findings
    metadata["pathological_count"] = len(findings)
    metadata["pathological_findings_source"] = "deterministic_backend_only"
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_pathological_findings
