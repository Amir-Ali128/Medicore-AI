"""Canonical laboratory ingestion contract.

Every MediCore lab source is normalized into this source-preserving structure before
native C++ validation. This layer performs no clinical interpretation and never
silently repairs ambiguous measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from typing import Any, Mapping, Sequence

CANONICAL_LAB_CONTRACT = "medicore-canonical-lab-v1"
CANONICAL_ROW_CONTRACT = "medicore-canonical-lab-row-v1"

SOURCE_ENABIZ_PDF = "enabiz_pdf"
SOURCE_FILE_UPLOAD = "file_upload"
SOURCE_PHOTO = "photo"
SOURCE_SCREENSHOT = "screenshot"
SOURCE_MANUAL = "manual"
SOURCE_EMAIL_ATTACHMENT = "email_attachment"
SOURCE_INTEGRATION = "integration"

CANONICAL_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        SOURCE_ENABIZ_PDF,
        SOURCE_FILE_UPLOAD,
        SOURCE_PHOTO,
        SOURCE_SCREENSHOT,
        SOURCE_MANUAL,
        SOURCE_EMAIL_ATTACHMENT,
        SOURCE_INTEGRATION,
    }
)


@dataclass(frozen=True, slots=True)
class SourceContext:
    source_type: str
    file_name: str | None = None
    source_sha256: str | None = None
    source_record_id: str | None = None
    integration_type: str | None = None

    def __post_init__(self) -> None:
        if self.source_type not in CANONICAL_SOURCE_TYPES:
            raise ValueError(f"Desteklenmeyen laboratuvar giriş kaynağı: {self.source_type}")


def content_sha256(content: bytes) -> str:
    return sha256(content).hexdigest()


def _text(value: Any, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit] if limit is not None else text


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _confidence(value: Any, default: float) -> float:
    number = _float(value)
    if number is None:
        number = default
    return max(0.0, min(1.0, number))


def _page(value: Any) -> int | None:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page >= 1 else None


def _age(value: Any) -> float | None:
    number = _float(value)
    if number is None or number < 0 or number > 130:
        return None
    return number


def _first_present(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _row_name(row: Mapping[str, Any]) -> str | None:
    return _text(
        row.get("raw_parameter_name")
        or row.get("parameter_name")
        or row.get("test_name")
        or row.get("name")
        or row.get("display_name"),
        limit=255,
    )


def canonicalize_row(
    row: Mapping[str, Any],
    *,
    source: SourceContext,
    default_confidence: float,
    default_page: int | None = None,
) -> dict[str, Any]:
    """Convert one extracted/structured result into the stable canonical row.

    No reference parsing, unit conversion, plausibility correction or result
    classification is performed here. Those are deterministic native-core duties.
    """
    raw_name = _row_name(row)
    raw_value = _text(_first_present(row, "raw_value", "result", "value"), limit=256)

    normalized_source = _first_present(row, "normalized_value", "numeric_value")
    if normalized_source is None:
        candidate = row.get("value")
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            normalized_source = candidate
    normalized_value = _float(normalized_source)

    raw_unit = _text(_first_present(row, "raw_unit", "unit"), limit=64)
    unit = _text(_first_present(row, "unit", "normalized_unit", "raw_unit"), limit=64)
    confidence = _confidence(
        _first_present(row, "confidence", "extraction_confidence"),
        default_confidence,
    )

    reasons: list[str] = []
    if not raw_name:
        reasons.append("missing_parameter_name")
    if raw_value is None and normalized_value is None:
        reasons.append("missing_observed_value")
    if confidence < 0.85:
        reasons.append("low_input_confidence")

    needs_review = bool(row.get("needs_review")) or bool(reasons)
    source_file_name = _text(row.get("source_file_name") or source.file_name, limit=512)
    source_page = _page(row.get("source_page")) or default_page
    row_record_id = _text(row.get("source_record_id"), limit=256)

    return {
        "canonical_row_contract": CANONICAL_ROW_CONTRACT,
        "raw_parameter_name": raw_name or "",
        "canonical_name": _text(row.get("canonical_name"), limit=255),
        "loinc_code": _text(_first_present(row, "loinc_code", "loinc"), limit=64),
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "raw_unit": raw_unit,
        "unit": unit,
        "reference_min": _float(_first_present(row, "reference_min", "ref_min")),
        "reference_max": _float(_first_present(row, "reference_max", "ref_max")),
        "reference_text": _text(_first_present(row, "reference_text", "reference_range"), limit=512),
        "reference_type": _text(row.get("reference_type"), limit=64),
        "measured_at": _text(_first_present(row, "measured_at", "observed_at"), limit=64),
        "value_type": _text(row.get("value_type"), limit=32)
        or ("numeric" if normalized_value is not None else "qualitative" if raw_value is not None else "unknown"),
        "needs_review": needs_review,
        "confidence": confidence,
        "ingestion_reasons": reasons,
        "source_type": source.source_type,
        "source_file_name": source_file_name,
        "source_page": source_page,
        "source_sha256": source.source_sha256,
        "source_record_id": row_record_id or source.source_record_id,
        "integration_type": source.integration_type,
    }


def build_canonical_case(
    *,
    source: SourceContext,
    rows: Sequence[Mapping[str, Any]],
    patient_age: Any = None,
    patient_sex: Any = None,
    report_date: Any = None,
    warnings: Sequence[Any] | None = None,
    extraction_confidence: Any = None,
    default_confidence: float = 1.0,
) -> dict[str, Any]:
    canonical_rows = [
        canonicalize_row(row, source=source, default_confidence=default_confidence)
        for row in rows
    ]
    if not canonical_rows:
        raise ValueError("Canonical laboratuvar vakası için en az bir sonuç gerekir.")

    case_confidence = _float(extraction_confidence)
    if case_confidence is None:
        case_confidence = min((float(row["confidence"]) for row in canonical_rows), default=default_confidence)
    case_confidence = max(0.0, min(1.0, case_confidence))

    safe_warnings = [str(item)[:1000] for item in (warnings or []) if str(item).strip()]
    return {
        "contract_version": CANONICAL_LAB_CONTRACT,
        "source_type": source.source_type,
        "source": {
            "type": source.source_type,
            "file_name": source.file_name,
            "sha256": source.source_sha256,
            "record_id": source.source_record_id,
            "integration_type": source.integration_type,
        },
        "patient_age": _age(patient_age),
        "patient_sex": _text(patient_sex, limit=32),
        "report_date": _text(report_date, limit=64),
        "labs": canonical_rows,
        "warnings": safe_warnings,
        "extraction_confidence": case_confidence,
        "needs_review": any(bool(row["needs_review"]) for row in canonical_rows),
        "native_ready": True,
    }


def canonicalize_extraction_payload(
    payload: Mapping[str, Any],
    *,
    source: SourceContext,
) -> dict[str, Any]:
    labs = payload.get("labs")
    if not isinstance(labs, Sequence) or isinstance(labs, (str, bytes, bytearray)):
        raise ValueError("Extraction payload laboratuvar satırları içermiyor.")
    rows = [item for item in labs if isinstance(item, Mapping)]
    warnings = payload.get("warnings")
    if not isinstance(warnings, Sequence) or isinstance(warnings, (str, bytes, bytearray)):
        warnings = None
    return build_canonical_case(
        source=source,
        rows=rows,
        patient_age=payload.get("patient_age"),
        patient_sex=payload.get("patient_sex"),
        report_date=payload.get("report_date"),
        warnings=warnings,
        extraction_confidence=payload.get("extraction_confidence"),
        default_confidence=0.85,
    )
