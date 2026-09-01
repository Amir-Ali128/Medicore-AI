"""Expose deterministic pathological findings without increasing LLM context.

Only HIGH/LOW laboratory results are turned into the structured abnormal-lab report.
Each item includes the measured value, meaningful reference boundary, and a concise
explanation of why it was classified high or low. These details are for the UI and
are not added to the Claude prompt.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
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

_SENTINEL_ABS = Decimal("999999999")


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def _decimal(value: object) -> Decimal | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        parsed = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if abs(parsed) >= _SENTINEL_ABS:
        return None
    return parsed


def _number_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _reference_text(
    low: Decimal | None,
    high: Decimal | None,
    unit: str | None,
) -> str | None:
    low_text = _number_text(low)
    high_text = _number_text(high)
    suffix = f" {unit}" if unit else ""
    if low_text is not None and high_text is not None:
        return f"{low_text} - {high_text}{suffix}"
    if high_text is not None:
        return f"< {high_text}{suffix}"
    if low_text is not None:
        return f"> {low_text}{suffix}"
    return None


def _classification_reason(
    *,
    status: str,
    value: Decimal | None,
    low: Decimal | None,
    high: Decimal | None,
    unit: str | None,
    fallback: str | None,
) -> tuple[str, float | None]:
    value_text = _number_text(value)
    suffix = f" {unit}" if unit else ""

    if status == "high" and value is not None and high is not None:
        delta = value - high
        delta_text = _number_text(delta)
        percent = float((delta / high) * Decimal("100")) if high != 0 else None
        reason = (
            f"Sonuç {value_text}{suffix}; referans üst sınırı {_number_text(high)}{suffix}. "
            f"Üst sınırın {delta_text}{suffix} üzerinde olduğu için yüksek sınıflandırıldı."
        )
        return reason, round(percent, 1) if percent is not None else None

    if status == "low" and value is not None and low is not None:
        delta = low - value
        delta_text = _number_text(delta)
        percent = float((delta / low) * Decimal("100")) if low != 0 else None
        reason = (
            f"Sonuç {value_text}{suffix}; referans alt sınırı {_number_text(low)}{suffix}. "
            f"Alt sınırın {delta_text}{suffix} altında olduğu için düşük sınıflandırıldı."
        )
        return reason, round(percent, 1) if percent is not None else None

    if fallback:
        return fallback, None
    direction = "yüksek" if status == "high" else "düşük"
    return f"Sistem bu sonucu PDF referansına göre {direction} sınıflandırdı.", None


def _pathological_findings(
    evidence: list[dict[str, Any]], flags: list[str]
) -> list[dict[str, Any]]:
    """Return deterministic HIGH/LOW laboratory and vital findings only."""

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in evidence:
        status = str(item.get("result_status") or "").lower()
        if status not in {"high", "low"}:
            continue

        name = _clean(item.get("parameter_name")) or _clean(item.get("parameter_code"))
        if not name:
            name = "Laboratuvar parametresi"
        value_text = _clean(item.get("value"))
        unit = _clean(item.get("unit"))
        value = _decimal(item.get("value"))
        low = _decimal(item.get("reference_min"))
        high = _decimal(item.get("reference_max"))
        direction = "yüksek" if status == "high" else "düşük"
        key = (name.casefold(), status)
        if key in seen:
            continue
        seen.add(key)

        reference = _reference_text(low, high, unit)
        explanation, deviation_percent = _classification_reason(
            status=status,
            value=value,
            low=low,
            high=high,
            unit=unit,
            fallback=_clean(item.get("classification_reason")),
        )
        measured = " ".join(part for part in (value_text, unit) if part) or None

        findings.append(
            {
                "source": "laboratory",
                "name": name,
                "status": status,
                "status_label": direction,
                "value": value_text,
                "unit": unit,
                "reference_min": _number_text(low),
                "reference_max": _number_text(high),
                "reference_text": reference,
                "classification_reason": explanation,
                "deviation_percent": deviation_percent,
                "backend_reason": _clean(item.get("classification_reason")),
                "display": f"{name}: {measured} ({direction})"
                if measured
                else f"{name}: {direction}",
            }
        )

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
                "reference_min": None,
                "reference_max": None,
                "reference_text": None,
                "classification_reason": None,
                "deviation_percent": None,
                "backend_reason": None,
                "display": f"{name}: {label}",
            }
        )

    return findings[:30]


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
    metadata["pathological_findings_source"] = "deterministic_backend_reference_comparison"
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_pathological_findings
