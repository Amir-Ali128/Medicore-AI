"""Arithmetic/source consistency only. Values, units and printed ranges are immutable."""
from copy import deepcopy
from datetime import date, datetime
import math
import re

from app.domain import consistency_config as cfg
from app.domain.alias_engine import curated_consistency_name
from app.domain.lab_result_classification import classify_lab_result, normalize_lab_unit


def number(value):
    if value is None or isinstance(value, bool) or not re.fullmatch(r'[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][+-]?\d+)?', str(value).strip()):
        return None
    try:
        result = float(str(value).replace(',', '.'))
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError):
        return None


def mark(rows, code):
    for row in rows:
        reasons = row.get('ingestion_reasons')
        reasons = [reasons] if isinstance(reasons, str) else list(reasons or [])
        row['ingestion_reasons'] = list(dict.fromkeys([*reasons, code]))
        row['needs_review'] = True


def day(row):
    for field in cfg.DATE_FIELDS:
        value = row.get(field)
        if value:
            try:
                return date.fromisoformat(str(value)[:10]).isoformat()
            except (ValueError, TypeError):
                continue
    return None


def value(row):
    return number(row.get('raw_value') if row.get('raw_value') not in (None, '') else row.get('normalized_value', row.get('value')))


def factor(row, units):
    scale = units.get(normalize_lab_unit(row.get('unit')))
    if scale is None:
        mark([row], 'consistency_unit_unresolved')
    return scale


def annotate_lab_case(case):
    result = deepcopy(case)
    rows = [row for row in (result.get('labs') or []) if isinstance(row, dict)]
    if not rows: return result
    database_ranges = result.get('database_ranges') if isinstance(result.get('database_ranges'), dict) else {}
    groups = {}
    for row in rows:
        name = curated_consistency_name(row.get('canonical_name') or row.get('raw_parameter_name') or row.get('test_name'), row.get('unit'))
        observed = value(row)
        when = day(row)
        if name and when:
            groups.setdefault(when, {}).setdefault(name, []).append(row)
        classified = classify_lab_result(value=row.get('raw_value', row.get('value')), unit=row.get('unit'), reference_text=row.get('reference_text'),
            reference_low=row.get('reference_min'), reference_high=row.get('reference_max'), reference_unit=row.get('reference_unit'), ingestion_reasons=row.get('ingestion_reasons', []))
        flag = str(row.get('source_flag') or '').casefold().translate(str.maketrans('ıüşöçğ','iusocg'))
        direction = cfg.SOURCE_DIRECTIONS.get(flag)
        status = row.get('status', classified.status)
        if direction and status != 'UNKNOWN' and direction != status:
            mark([row], 'source_flag_status_conflict')
        low, high = classified.reference_low, classified.reference_high
        if observed is None or (low is None and high is None):
            continue
        unit = normalize_lab_unit(row.get('unit'))
        ref_unit = normalize_lab_unit(row.get('reference_unit'))
        if unit not in cfg.KNOWN_UNITS or (ref_unit and ref_unit != unit):
            mark([row], 'consistency_unit_unresolved'); continue
        outside = (low is not None and observed < low) or (high is not None and observed > high)
        if outside and not flag:
            mark([row], 'value_outside_reference_no_flag')
        if not outside and direction:
            mark([row], 'flag_without_reference_breach')
        if (high is not None and high > 0 and observed > high * cfg.MAGNITUDE_FACTOR) or (low is not None and low > 0 and observed < low / cfg.MAGNITUDE_FACTOR):
            mark([row], 'magnitude_suspect')
        reference = database_ranges.get(name)
        if isinstance(reference, dict):
            dbunit = normalize_lab_unit(reference.get('unit'))
            scale = 1.0
            if dbunit != unit:
                table = cfg.PROTEIN_UNIT_FACTORS if name in cfg.PROTEIN_NAMES else cfg.CELL_UNIT_FACTORS
                if unit not in table or dbunit not in table:
                    mark([row], 'consistency_unit_unresolved'); continue
                scale = table[dbunit] / table[unit]
            ratios = []
            for printed, key in ((low,'minimum'),(high,'maximum')):
                database = number(reference.get(key))
                if printed is not None and printed > 0 and database is not None and database > 0:
                    database *= scale
                    ratios.append(max(printed / database, database / printed))
            if ratios and max(ratios) > cfg.REFERENCE_DIVERGENCE_FACTOR:
                mark([row], 'printed_reference_divergence')
    for group in groups.values():
        def unique(names):
            return [group[name][0] for name in names] if all(len(group.get(name, [])) == 1 for name in names) else None
        percentages = unique([name + ' %' for name in cfg.DIFFERENTIAL_NAMES])
        if percentages and all(value(row) is not None for row in percentages):
            valid = [normalize_lab_unit(row.get('unit')) in cfg.PERCENT_UNITS for row in percentages]
            for row, ok in zip(percentages, valid):
                if not ok: mark([row], 'consistency_unit_unresolved')
            if all(valid) and abs(math.fsum(value(row) for row in percentages) - 100) > cfg.DIFF_SUM_TOLERANCE + cfg.EPSILON:
                mark(percentages, 'differential_sum_mismatch')
        for name in cfg.DIFFERENTIAL_NAMES:
            cells = unique([name, name + ' %', 'Lökosit'])
            if not cells or any(value(row) is None for row in cells): continue
            absolute, percent, wbc = cells
            left, right = factor(absolute, cfg.CELL_UNIT_FACTORS), factor(wbc, cfg.CELL_UNIT_FACTORS)
            if normalize_lab_unit(percent.get('unit')) not in cfg.PERCENT_UNITS:
                mark([percent], 'consistency_unit_unresolved'); continue
            if left is None or right is None: continue
            expected = value(percent) * value(wbc) * right / 100
            actual = value(absolute) * left
            mismatch = abs(actual - expected) > cfg.EPSILON if abs(expected) <= cfg.EPSILON else abs(actual - expected) / abs(expected) > cfg.ABS_PCT_TOLERANCE + cfg.EPSILON
            if mismatch: mark(cells, 'absolute_percent_mismatch')
        proteins = unique(cfg.PROTEIN_NAMES)
        if proteins and not any(proteins[2].get(key) for key in cfg.DERIVED_FIELDS) and all(value(row) is not None for row in proteins):
            scales = [factor(row, cfg.PROTEIN_UNIT_FACTORS) for row in proteins]
            if all(scale is not None for scale in scales) and abs(value(proteins[0])*scales[0] - value(proteins[1])*scales[1] - value(proteins[2])*scales[2]) > cfg.PROTEIN_TOLERANCE + cfg.EPSILON:
                mark(proteins, 'protein_sum_mismatch')
    if any(row.get('needs_review') for row in rows): result['needs_review'] = True
    return result


def annotate_request(payload, database_ranges=None):
    from app.core.config import get_settings
    if getattr(get_settings(), 'report_consistency_enabled', False):
        from app.domain.report_consistency import apply_report_consistency
        payload = apply_report_consistency(payload)
    if not getattr(get_settings(), 'lab_consistency_rules_enabled', False): return payload
    from app.domain.simple_case import normalize_simple_case
    from app.domain.consistency_flags import collect_consistency_flags
    normalized = normalize_simple_case(payload)
    raw = []
    for lab, selected in zip(payload.labs, normalized.labs):
        raw.append({**lab.source_metadata, 'raw_parameter_name': lab.test_name, 'raw_value': lab.value, 'unit': lab.unit,
                    'reference_min': selected.reference_low, 'reference_max': selected.reference_high,
                    'reference_text': selected.reference_text, 'status': selected.status,
                    **{field: getattr(lab, field, None) or lab.source_metadata.get(field) for field in cfg.DATE_FIELDS}})
    annotated = annotate_lab_case({'labs':raw, 'database_ranges': database_ranges or {}})
    labs = []
    for lab, row in zip(payload.labs, annotated['labs']):
        metadata = dict(lab.source_metadata)
        if row.get('ingestion_reasons'):
            metadata.update(ingestion_reasons=row['ingestion_reasons'], needs_review=bool(row.get('needs_review')))
        lab = lab.model_copy(update={'source_metadata':metadata})
        if getattr(get_settings(), 'consistency_section_enabled', False):
            metadata['consistency_flags'] = collect_consistency_flags(payload.model_copy(update={'labs':[lab], 'reports':[]}))
        labs.append(lab)
    return payload.model_copy(update={'labs':labs})


async def annotate_request_with_database(payload, session):
    from app.core.config import get_settings
    if getattr(get_settings(), 'report_consistency_enabled', False):
        from app.domain.report_consistency import apply_report_consistency
        payload = apply_report_consistency(payload)
    if not getattr(get_settings(), 'lab_consistency_rules_enabled', False): return payload
    ranges = {}
    if any(lab.source_reference or lab.source_references for lab in payload.labs) and payload.clinical.age is not None and payload.clinical.sex in ('male','female'):
        from app.domain.enums import Sex
        from app.domain.reference_resolver import ReferenceResolver
        from app.infrastructure.database.repositories.clinical_parameter_repository import ClinicalParameterRepository
        from app.infrastructure.database.repositories.reference_range_repository import ReferenceRangeRepository
        from app.schemas.analysis import ReferenceResolutionRequest
        parameters = ClinicalParameterRepository(session)
        catalog = await parameters.list_all()
        resolver = ReferenceResolver(ReferenceRangeRepository(session), parameters)
        for name in {curated_consistency_name(lab.test_name, lab.unit) for lab in payload.labs} - {None}:
            matches = [item for item in catalog if curated_consistency_name(item.canonical_name) == name or curated_consistency_name(item.parameter_code) == name]
            if len(matches) != 1: continue
            parameter = matches[0]
            selected = await resolver.resolve(ReferenceResolutionRequest(canonical_parameter_id=parameter.id, parameter_code=parameter.parameter_code,
                patient_age=payload.clinical.age, patient_sex=Sex(payload.clinical.sex)))
            if not selected.needs_review:
                ranges[name] = {'minimum':selected.reference_min, 'maximum':selected.reference_max, 'unit':selected.unit}
    return annotate_request(payload, ranges)
