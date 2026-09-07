"""Seven-source laboratory ingestion gateway.

The gateway terminates source-specific formats and emits only
``medicore-canonical-lab-v1``. It deliberately stops before native C++ validation;
that boundary is wired in the next pipeline phase.
"""

from __future__ import annotations

import csv
from datetime import datetime
import io
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from app.domain.canonical_lab_model import (
    CANONICAL_LAB_CONTRACT,
    SOURCE_EMAIL_ATTACHMENT,
    SOURCE_ENABIZ_PDF,
    SOURCE_FILE_UPLOAD,
    SOURCE_INTEGRATION,
    SOURCE_MANUAL,
    SOURCE_PHOTO,
    SOURCE_SCREENSHOT,
    SourceContext,
    build_canonical_case,
    canonicalize_extraction_payload,
    content_sha256,
)
from app.domain.openai_lab_extraction_service import (
    SUPPORTED_LAB_MEDIA_TYPES,
    extract_lab_document_with_openai,
)

SUPPORTED_STRUCTURED_FILE_TYPES: frozenset[str] = frozenset(
    {"application/json", "text/csv", "application/csv", "text/plain"}
)
SUPPORTED_GENERIC_FILE_TYPES: frozenset[str] = frozenset(
    set(SUPPORTED_LAB_MEDIA_TYPES) | set(SUPPORTED_STRUCTURED_FILE_TYPES)
)
_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)$")

INGESTION_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {"source_type": SOURCE_ENABIZ_PDF, "input": "file", "formats": ["application/pdf"]},
    {"source_type": SOURCE_FILE_UPLOAD, "input": "file", "formats": sorted(SUPPORTED_GENERIC_FILE_TYPES)},
    {"source_type": SOURCE_PHOTO, "input": "file", "formats": sorted(_IMAGE_TYPES)},
    {"source_type": SOURCE_SCREENSHOT, "input": "file", "formats": sorted(_IMAGE_TYPES)},
    {"source_type": SOURCE_MANUAL, "input": "structured", "formats": ["json"]},
    {"source_type": SOURCE_EMAIL_ATTACHMENT, "input": "file", "formats": sorted(SUPPORTED_GENERIC_FILE_TYPES)},
    {
        "source_type": SOURCE_INTEGRATION,
        "input": "structured",
        "formats": ["hl7_oru", "fhir", "rest"],
    },
)


def ingestion_capabilities() -> dict[str, Any]:
    return {
        "contract_version": CANONICAL_LAB_CONTRACT,
        "source_count": len(INGESTION_CAPABILITIES),
        "sources": [dict(item) for item in INGESTION_CAPABILITIES],
    }


def _normalized_media_type(media_type: str | None, file_name: str | None = None) -> str:
    declared = (media_type or "").split(";", 1)[0].strip().lower()
    if declared and declared != "application/octet-stream":
        return declared
    suffix = Path(file_name or "").suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".json": "application/json",
        ".csv": "text/csv",
        ".hl7": "text/plain",
        ".txt": "text/plain",
    }.get(suffix, declared)


def _strict_numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    if not text or not _NUMERIC_RE.fullmatch(text):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _source(
    *,
    source_type: str,
    content: bytes | None = None,
    file_name: str | None = None,
    source_record_id: str | None = None,
    integration_type: str | None = None,
) -> SourceContext:
    return SourceContext(
        source_type=source_type,
        file_name=file_name,
        source_sha256=content_sha256(content) if content is not None else None,
        source_record_id=(str(source_record_id).strip()[:256] if source_record_id else None),
        integration_type=integration_type,
    )


async def ingest_document_bytes(
    *,
    content: bytes,
    media_type: str,
    file_name: str,
    source_type: str,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    if not content:
        raise ValueError("Laboratuvar kaynağı boş olamaz.")
    normalized_type = _normalized_media_type(media_type, file_name)
    if normalized_type not in SUPPORTED_LAB_MEDIA_TYPES:
        raise ValueError(f"Bu giriş için desteklenmeyen dosya türü: {normalized_type or 'unknown'}")
    if source_type == SOURCE_ENABIZ_PDF and normalized_type != "application/pdf":
        raise ValueError("e-Nabız girişi PDF olmalıdır.")
    if source_type in {SOURCE_PHOTO, SOURCE_SCREENSHOT} and normalized_type not in _IMAGE_TYPES:
        raise ValueError("Fotoğraf/ekran görüntüsü girişi PNG, JPEG veya WebP olmalıdır.")

    payload = await extract_lab_document_with_openai(
        content=content,
        media_type=normalized_type,
        file_name=file_name,
    )
    return canonicalize_extraction_payload(
        payload,
        source=_source(
            source_type=source_type,
            content=content,
            file_name=file_name,
            source_record_id=source_record_id,
        ),
    )


def ingest_manual_payload(
    *,
    labs: Sequence[Mapping[str, Any]],
    patient_age: Any = None,
    patient_sex: Any = None,
    report_date: Any = None,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    return build_canonical_case(
        source=_source(source_type=SOURCE_MANUAL, source_record_id=source_record_id),
        rows=labs,
        patient_age=patient_age,
        patient_sex=patient_sex,
        report_date=report_date,
        warnings=[],
        extraction_confidence=1.0,
        default_confidence=1.0,
    )


def _csv_rows(content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV dosyası UTF-8 olarak okunamadı.") from exc
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for source in reader:
        row = {str(key).strip(): value for key, value in source.items() if key is not None}
        raw_value = row.get("raw_value") or row.get("value") or row.get("result")
        if "normalized_value" not in row or not str(row.get("normalized_value") or "").strip():
            row["normalized_value"] = _strict_numeric(raw_value)
        rows.append(row)
    if not rows:
        raise ValueError("CSV dosyasında laboratuvar satırı bulunamadı.")
    return rows


def _json_payload(content: bytes) -> Any:
    try:
        return json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON laboratuvar dosyası geçerli değil.") from exc


def _rest_rows(payload: Any) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    metadata: Mapping[str, Any] = {}
    if isinstance(payload, Mapping):
        candidate = payload.get("labs")
        if not isinstance(candidate, list):
            candidate = payload.get("results")
        if not isinstance(candidate, list):
            candidate = payload.get("observations")
        if isinstance(candidate, list):
            metadata = payload
            return [item for item in candidate if isinstance(item, Mapping)], metadata
        # A single result object is accepted only when it clearly looks like a row.
        if any(key in payload for key in ("raw_parameter_name", "test_name", "name")):
            return [payload], {}
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)], {}
    raise ValueError("REST/JSON payload laboratuvar sonuç listesi içermiyor.")


def ingest_rest_payload(
    payload: Any,
    *,
    source_record_id: str | None = None,
    source_type: str = SOURCE_INTEGRATION,
    file_name: str | None = None,
    source_hash: str | None = None,
) -> dict[str, Any]:
    rows, metadata = _rest_rows(payload)
    if not rows:
        raise ValueError("REST/JSON payload içinde laboratuvar sonucu bulunamadı.")
    source = SourceContext(
        source_type=source_type,
        file_name=file_name,
        source_sha256=source_hash,
        source_record_id=source_record_id,
        integration_type="rest" if source_type == SOURCE_INTEGRATION else None,
    )
    return build_canonical_case(
        source=source,
        rows=rows,
        patient_age=metadata.get("patient_age"),
        patient_sex=metadata.get("patient_sex"),
        report_date=metadata.get("report_date"),
        warnings=metadata.get("warnings") if isinstance(metadata.get("warnings"), list) else [],
        extraction_confidence=metadata.get("extraction_confidence", 1.0),
        default_confidence=1.0,
    )


def _hl7_datetime(value: str | None) -> str | None:
    text = (value or "").strip()
    if len(text) < 8 or not text[:8].isdigit():
        return text or None
    try:
        parsed = datetime.strptime(text[:14] if len(text) >= 14 else text[:8], "%Y%m%d%H%M%S" if len(text) >= 14 else "%Y%m%d")
    except ValueError:
        return text[:64]
    return parsed.isoformat()


def ingest_hl7_oru(
    message: str,
    *,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("HL7 mesajı boş olamaz.")
    segments = [segment.strip() for segment in re.split(r"[\r\n]+", message) if segment.strip()]
    if not segments or not segments[0].startswith("MSH|"):
        raise ValueError("HL7 mesajı geçerli bir MSH segmenti ile başlamıyor.")

    control_id = source_record_id
    patient_sex: str | None = None
    report_date: str | None = None
    rows: list[dict[str, Any]] = []

    for segment in segments:
        fields = segment.split("|")
        kind = fields[0]
        if kind == "MSH" and not control_id and len(fields) > 9:
            control_id = fields[9].strip() or None
        elif kind == "PID" and len(fields) > 8:
            # Only coarse sex is retained; patient names, identifiers and DOB never
            # enter the canonical ingestion contract.
            patient_sex = fields[8].strip()[:32] or None
        elif kind == "OBR" and len(fields) > 7:
            report_date = _hl7_datetime(fields[7]) or report_date
        elif kind == "OBX" and len(fields) > 5:
            observation = fields[3].split("^") if len(fields) > 3 else []
            code = observation[0].strip() if observation else ""
            display = observation[1].strip() if len(observation) > 1 else code
            system = observation[2].strip() if len(observation) > 2 else ""
            raw_value = fields[5].strip() if len(fields) > 5 else ""
            unit = fields[6].split("^")[0].strip() if len(fields) > 6 else ""
            reference_text = fields[7].strip() if len(fields) > 7 else ""
            value_type = fields[2].strip().upper() if len(fields) > 2 else ""
            rows.append(
                {
                    "raw_parameter_name": display or code,
                    "canonical_name": None,
                    "loinc_code": code if system.upper() in {"LN", "LOINC"} or "LOINC" in system.upper() else None,
                    "raw_value": raw_value or None,
                    "normalized_value": _strict_numeric(raw_value) if value_type in {"NM", "SN"} else None,
                    "unit": unit or None,
                    "reference_text": reference_text or None,
                    "measured_at": report_date,
                    "value_type": "numeric" if value_type in {"NM", "SN"} else "qualitative",
                    "confidence": 1.0,
                    "needs_review": False,
                }
            )

    if not rows:
        raise ValueError("HL7 mesajında OBX laboratuvar sonucu bulunamadı.")
    return build_canonical_case(
        source=_source(
            source_type=SOURCE_INTEGRATION,
            source_record_id=control_id,
            integration_type="hl7_oru",
        ),
        rows=rows,
        patient_age=None,
        patient_sex=patient_sex,
        report_date=report_date,
        extraction_confidence=1.0,
        default_confidence=1.0,
    )


def _coding_name(code: Mapping[str, Any]) -> tuple[str, str | None]:
    text = str(code.get("text") or "").strip()
    coding = code.get("coding")
    if not isinstance(coding, list):
        return text, None
    display = text
    loinc: str | None = None
    for item in coding:
        if not isinstance(item, Mapping):
            continue
        if not display:
            display = str(item.get("display") or item.get("code") or "").strip()
        system = str(item.get("system") or "").lower()
        if "loinc.org" in system:
            loinc = str(item.get("code") or "").strip() or None
    return display, loinc


def _fhir_observations(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    resource_type = str(payload.get("resourceType") or "")
    if resource_type == "Observation":
        return [payload]
    if resource_type == "Bundle":
        rows: list[Mapping[str, Any]] = []
        for entry in payload.get("entry") or []:
            if not isinstance(entry, Mapping):
                continue
            resource = entry.get("resource")
            if isinstance(resource, Mapping) and resource.get("resourceType") == "Observation":
                rows.append(resource)
        return rows
    if resource_type == "DiagnosticReport":
        contained = payload.get("contained") or []
        return [
            item
            for item in contained
            if isinstance(item, Mapping) and item.get("resourceType") == "Observation"
        ]
    return []


def ingest_fhir(
    payload: Mapping[str, Any],
    *,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("FHIR payload JSON object olmalıdır.")
    observations = _fhir_observations(payload)
    if not observations:
        raise ValueError("FHIR payload içinde gömülü Observation sonucu bulunamadı.")

    rows: list[dict[str, Any]] = []
    report_date: str | None = None
    for observation in observations:
        code = observation.get("code") if isinstance(observation.get("code"), Mapping) else {}
        display, loinc = _coding_name(code)
        quantity = observation.get("valueQuantity")
        raw_value: Any = None
        normalized_value: float | None = None
        unit: str | None = None
        value_type = "unknown"
        if isinstance(quantity, Mapping):
            raw_value = quantity.get("value")
            normalized_value = _strict_numeric(raw_value)
            unit = str(quantity.get("unit") or quantity.get("code") or "").strip() or None
            value_type = "numeric"
        elif observation.get("valueString") is not None:
            raw_value = observation.get("valueString")
            value_type = "qualitative"
        elif isinstance(observation.get("valueCodeableConcept"), Mapping):
            concept = observation["valueCodeableConcept"]
            raw_value = concept.get("text")
            if raw_value is None and isinstance(concept.get("coding"), list) and concept["coding"]:
                first = concept["coding"][0]
                if isinstance(first, Mapping):
                    raw_value = first.get("display") or first.get("code")
            value_type = "qualitative"

        reference_text: str | None = None
        reference_min: Any = None
        reference_max: Any = None
        ranges = observation.get("referenceRange")
        if isinstance(ranges, list) and ranges and isinstance(ranges[0], Mapping):
            reference = ranges[0]
            low = reference.get("low")
            high = reference.get("high")
            if isinstance(low, Mapping):
                reference_min = low.get("value")
            if isinstance(high, Mapping):
                reference_max = high.get("value")
            reference_text = str(reference.get("text") or "").strip() or None

        measured_at = str(
            observation.get("effectiveDateTime")
            or observation.get("effectiveInstant")
            or observation.get("issued")
            or ""
        ).strip() or None
        report_date = report_date or measured_at
        rows.append(
            {
                "raw_parameter_name": display,
                "canonical_name": None,
                "loinc_code": loinc,
                "raw_value": None if raw_value is None else str(raw_value),
                "normalized_value": normalized_value,
                "unit": unit,
                "reference_min": reference_min,
                "reference_max": reference_max,
                "reference_text": reference_text,
                "measured_at": measured_at,
                "value_type": value_type,
                "confidence": 1.0,
                "needs_review": False,
                "source_record_id": observation.get("id"),
            }
        )

    bundle_id = source_record_id or str(payload.get("id") or "").strip() or None
    return build_canonical_case(
        source=_source(
            source_type=SOURCE_INTEGRATION,
            source_record_id=bundle_id,
            integration_type="fhir",
        ),
        rows=rows,
        report_date=report_date,
        extraction_confidence=1.0,
        default_confidence=1.0,
    )


def ingest_integration_payload(
    *,
    integration_type: str,
    payload: Any,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    normalized = str(integration_type or "").strip().lower().replace("-", "_")
    if normalized in {"hl7", "hl7_oru", "oru"}:
        if not isinstance(payload, str):
            raise ValueError("HL7 entegrasyon payload'u metin olmalıdır.")
        return ingest_hl7_oru(payload, source_record_id=source_record_id)
    if normalized == "fhir":
        if not isinstance(payload, Mapping):
            raise ValueError("FHIR entegrasyon payload'u JSON object olmalıdır.")
        return ingest_fhir(payload, source_record_id=source_record_id)
    if normalized in {"rest", "api", "json"}:
        return ingest_rest_payload(payload, source_record_id=source_record_id)
    raise ValueError("integration_type hl7_oru, fhir veya rest olmalıdır.")


async def ingest_generic_file(
    *,
    content: bytes,
    media_type: str,
    file_name: str,
    source_type: str = SOURCE_FILE_UPLOAD,
    source_record_id: str | None = None,
) -> dict[str, Any]:
    if source_type not in {SOURCE_FILE_UPLOAD, SOURCE_EMAIL_ATTACHMENT}:
        raise ValueError("Generic dosya adapter'ı yalnızca file_upload veya email_attachment için kullanılabilir.")
    if not content:
        raise ValueError("Laboratuvar dosyası boş olamaz.")
    normalized_type = _normalized_media_type(media_type, file_name)
    if normalized_type in SUPPORTED_LAB_MEDIA_TYPES:
        return await ingest_document_bytes(
            content=content,
            media_type=normalized_type,
            file_name=file_name,
            source_type=source_type,
            source_record_id=source_record_id,
        )

    source = SourceContext(
        source_type=source_type,
        file_name=file_name,
        source_sha256=content_sha256(content),
        source_record_id=source_record_id,
        integration_type=None,
    )
    if normalized_type in {"text/csv", "application/csv"}:
        return build_canonical_case(
            source=source,
            rows=_csv_rows(content),
            extraction_confidence=1.0,
            default_confidence=1.0,
        )
    if normalized_type == "application/json":
        payload = _json_payload(content)
        rows, metadata = _rest_rows(payload)
        return build_canonical_case(
            source=source,
            rows=rows,
            patient_age=metadata.get("patient_age"),
            patient_sex=metadata.get("patient_sex"),
            report_date=metadata.get("report_date"),
            extraction_confidence=metadata.get("extraction_confidence", 1.0),
            default_confidence=1.0,
        )
    if normalized_type == "text/plain":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Metin dosyası UTF-8 olarak okunamadı.") from exc
        if text.lstrip().startswith("MSH|"):
            # Preserve the original upload source family while reusing the HL7 parser.
            canonical = ingest_hl7_oru(text, source_record_id=source_record_id)
            canonical["source_type"] = source_type
            canonical["source"] = {
                "type": source_type,
                "file_name": file_name,
                "sha256": content_sha256(content),
                "record_id": source_record_id,
                "integration_type": "hl7_oru_file",
            }
            for row in canonical["labs"]:
                row["source_type"] = source_type
                row["source_file_name"] = file_name
                row["source_sha256"] = content_sha256(content)
                row["integration_type"] = "hl7_oru_file"
            return canonical
        raise ValueError("text/plain dosyası için yalnızca HL7 ORU içeriği destekleniyor.")

    raise ValueError(f"Desteklenmeyen genel laboratuvar dosya türü: {normalized_type or 'unknown'}")
