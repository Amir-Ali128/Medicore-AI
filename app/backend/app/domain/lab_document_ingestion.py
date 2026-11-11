"""Read-only lab ingestion: normalize -> page extraction -> validation -> canonical rows.

UI classification and clinical reasoning are deliberately outside this module.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import math
import re
from typing import Any

from app.domain.canonical_lab_model import SourceContext, build_canonical_case, content_sha256
from app.domain.lab_document_normalizer import DocumentPage, normalize_document
from app.domain.lab_document_errors import LabDocumentReadError
from app.domain.lab_result_classification import normalize_lab_unit, parse_lab_observation

CONTRACT = 'medicore-lab-document-ingestion-v2'
INGESTION_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class RawLabRow:
    data: dict[str, Any]
    source_page: int
    source_row: int


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def validate_merge(rows: list[RawLabRow], source: SourceContext) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    seen: dict[tuple, dict[str, Any]] = {}
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw.data)
        name = _text(row.get('raw_parameter_name') or row.get('test_name') or row.get('canonical_name'))
        value = row.get('raw_value')
        if value is None or value == '':
            value = row.get('normalized_value')
        reasons = list(row.get('ingestion_reasons') or [])
        confidence = row.get('confidence', row.get('extraction_confidence'))
        try:
            if isinstance(confidence, bool):
                raise ValueError()
            confidence = 0.85 if confidence is None else float(confidence)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError()
        except (ValueError, TypeError):
            confidence = 0.0
            reasons.append('invalid_input_confidence')
        row['confidence'] = confidence
        if confidence < 0.85:
            reasons.append('low_input_confidence')
        if not name:
            reasons.append('missing_parameter_name')
        if value is None or value == '':
            reasons.append('missing_observed_value')
        numeric = row.get('normalized_value')
        observed = parse_lab_observation(value, row.get('unit'))
        if not _text(row.get('unit')) and not observed.inline_unit:
            reasons.append('missing_unit')
        if observed.error in ('observed_unit_mismatch', 'unverified_observed_unit'):
            reasons.append(observed.error)
        if numeric is not None:
            row['reader_normalized_value'] = str(numeric)
            supplied = parse_lab_observation(numeric)
            if supplied.error or supplied.comparator:
                reasons.append('invalid_numeric_value')
                row['normalized_value'] = None
            elif observed.number is None or observed.number != supplied.number:
                reasons.append('numeric_value_conflict')
                row['normalized_value'] = None
            else:
                row['normalized_value'] = float(observed.number) if not observed.comparator else None
        elif observed.number is not None and not observed.comparator:
            row['normalized_value'] = float(observed.number)
        if row.get('reference_unit') and row.get('unit') and normalize_lab_unit(row['reference_unit']) != normalize_lab_unit(row['unit']):
            reasons.append('reference_unit_mismatch')
        flag = _text(row.get('source_flag'))
        folded_flag = flag.casefold().translate(str.maketrans('ıüşöçğ', 'iusocg'))
        if flag and folded_flag not in {'normal','n','high','h','low','l','yuksek','dusuk','↑','↓','pozitif','negatif','positive','negative'}:
            reasons.append('unrecognized_source_status')
        lo, hi = row.get('reference_min'), row.get('reference_max')
        try:
            if any(v is not None and not math.isfinite(float(v)) for v in (lo, hi)) or (lo is not None and hi is not None and float(lo) > float(hi)):
                reasons.append('invalid_reference_bounds')
                row['reference_min'] = row['reference_max'] = None
        except (ValueError, TypeError):
            reasons.append('invalid_reference_bounds')
            row['reference_min'] = row['reference_max'] = None
        row.update(raw_parameter_name=name, raw_value=value, source_page=raw.source_page,
                   source_file_name=source.file_name, source_row=raw.source_row,
                   source_flag=flag or None, ingestion_reasons=list(dict.fromkeys(reasons)),
                   needs_review=bool(reasons) or bool(row.get('needs_review')))
        key = (name.casefold(), _text(value), _text(row.get('unit')).casefold(),
               _text(row.get('reference_text')), _text(row.get('reference_min')), _text(row.get('reference_max')), _text(row.get('reference_unit')),
               _text(row.get('measured_at')), _text(row.get('event_date')),
               _text(row.get('specimen_date')), _text(row.get('result_date')),
               _text(row.get('document_date')), flag.casefold())
        location = {'page': raw.source_page, 'row': raw.source_row}
        if key in seen:
            seen[key]['source_locations'].append(location)
            seen[key]['needs_review'] |= row['needs_review']
            seen[key]['confidence'] = min(seen[key]['confidence'], confidence)
            seen[key]['ingestion_reasons'] = list(dict.fromkeys(seen[key]['ingestion_reasons'] + reasons))
            continue
        row['source_locations'] = [location]
        seen[key] = row
        merged.append(row)
        group = (name.casefold(), _text(row.get('unit')).casefold(),
                 _text(row.get('measured_at')), _text(row.get('event_date')),
                 _text(row.get('specimen_date')), _text(row.get('result_date')),
                 _text(row.get('document_date')))
        groups.setdefault(group, []).append(row)
    for group in groups.values():
        if len(group) > 1:
            for row in group:
                row['needs_review'] = True
                row['ingestion_reasons'].append('conflicting_or_repeated_observation')
    case = build_canonical_case(source=source, rows=merged, default_confidence=0.85)
    for canonical, row in zip(case['labs'], merged):
        canonical.update(reader_normalized_value=row.get('reader_normalized_value'), reference_unit=row.get('reference_unit'), source_flag=row['source_flag'], source_row=row['source_row'],
                         source_locations=row['source_locations'],
                         ingestion_reasons=list(dict.fromkeys(canonical['ingestion_reasons'] + row['ingestion_reasons'])))
        canonical['needs_review'] |= row['needs_review']
    case['needs_review'] = any(row['needs_review'] for row in case['labs'])
    case['native_ready'] = False  # This pipeline validates in Python, without the removed native runtime.
    return case


def apply_consistency_rules(case: dict[str, Any]) -> dict[str, Any]:
    from app.core.config import get_settings
    if not getattr(get_settings(), 'lab_consistency_rules_enabled', False):
        return case
    from app.domain.lab_consistency_rules import annotate_lab_case
    return annotate_lab_case(case)


async def ingest_lab_document(
    *, content: bytes, media_type: str, file_name: str,
    extract_page: Callable[[DocumentPage], Awaitable[dict[str, Any] | None]],
    rotation: int = 0,
) -> dict[str, Any]:
    import asyncio
    pages = await asyncio.to_thread(normalize_document, content, media_type, rotation=rotation)
    semaphore = asyncio.Semaphore(2)
    async def read(page):
        async with semaphore:
            return await extract_page(page)
    try:
        page_results = await asyncio.wait_for(
            asyncio.gather(*(read(page) for page in pages)), timeout=INGESTION_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise ValueError('Belge okuma süre sınırını aştı. Daha az sayfayı birlikte yükleyin; tamamlanmamış sonuçlar kaydedilmedi.') from exc
    raw_rows: list[RawLabRow] = []
    warnings: list[str] = []
    page_reports = []
    for page, result in zip(pages, page_results):
        page_warnings = list(page.warnings)
        values = result.get('labs', []) if result else []
        values = [row for row in values if isinstance(row, Mapping)]
        expected = result.get('visible_row_count') if result else None
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
            expected = None
        if expected is None:
            page_warnings.append('visible_row_count_unverified')
        if expected is not None and expected != len(values):
            page_warnings.append('visible_row_count_mismatch')
        if not values:
            page_warnings.append('no_lab_rows_on_page_review')
        raw_rows.extend(RawLabRow(dict(row), page.number, index) for index, row in enumerate(values, 1))
        page_warnings.extend(str(w) for w in (result or {}).get('warnings', []))
        warnings.extend(f'page_{page.number}:{w}' for w in page_warnings)
        page_reports.append({'page':page.number, 'extracted_rows':len(values), 'visible_rows':expected,
                             'row_count_check':'unknown' if expected is None else 'matched' if expected == len(values) else 'mismatch',
                             'operations':page.operations, 'warnings':page_warnings,
                             'extraction_errors':(result or {}).get('extraction_errors', [])})
        from app.core.config import get_settings
        if getattr(get_settings(), 'lab_cross_read_enabled', False) and (result or {}).get('reader_reports'):
            page_reports[-1]['reader_reports'] = result['reader_reports']
    if not raw_rows:
        raise LabDocumentReadError(page_reports)
    source = SourceContext('file_upload' if media_type == 'application/pdf' else 'photo', file_name=file_name, source_sha256=content_sha256(content))
    case = validate_merge(raw_rows, source)
    from app.core.config import get_settings
    if getattr(get_settings(), 'lab_cross_read_enabled', False):
        from app.domain.lab_cross_read import restore_cross_read_metadata
        case = restore_cross_read_metadata(case, raw_rows)
    if getattr(get_settings(), 'lab_consistency_rules_enabled', False):
        from app.domain.consistency_config import DERIVED_FIELDS
        original = {(raw.source_page, raw.source_row): raw.data for raw in raw_rows}
        for row in case['labs']:
            for field in DERIVED_FIELDS:
                values = [original.get((loc['page'], loc['row']), {}).get(field) for loc in row['source_locations']]
                if any(values): row[field] = next(value for value in values if value)
        case = apply_consistency_rules(case)
    review_codes = {'low_resolution', 'blurred_image', 'low_contrast', 'visible_row_count_mismatch', 'no_lab_rows_on_page_review', 'page_extraction_failed', 'image_completeness_audit_failed'}
    review_pages = {p['page'] for p in page_reports if any(w in review_codes for w in p['warnings'])}
    for row in case['labs']:
        if any(loc['page'] in review_pages for loc in row['source_locations']):
            row['needs_review'] = True
    case.update(ingestion_contract=CONTRACT, warnings=warnings, page_reports=page_reports,
                raw_row_count=len(raw_rows), duplicate_count=len(raw_rows)-len(case['labs']),
                completeness_verified=False,  # No algorithm can certify that an unseen row is absent.
                needs_review=bool(warnings) or any(r['needs_review'] for r in case['labs']))
    return case
