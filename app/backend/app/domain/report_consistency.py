"""Source-report description checks, not diagnoses or corrections."""
from datetime import datetime
import re
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.domain import consistency_config as cfg
from app.domain.consistency_flags import codes, make_flag
from app.domain.document_dates import calendar_day
from app.domain.report_concepts import concept_polarities_text, fold_text


def _fold(text):
    return fold_text(str(text or '').translate(str.maketrans('ıİ','ii')))


def _organ_pattern(organ):
    return '(?:'+'|'.join(re.escape(term) for term in cfg.ORGAN_TERMS[organ])+')'


def _sides(text, organ):
    text = _fold(text); pattern = _organ_pattern(organ); result = set()
    for side, terms in cfg.SIDE_TERMS.items():
        side_pattern='(?:'+'|'.join(map(re.escape,terms))+')'
        if re.search(rf'\b{side_pattern}\s+{pattern}\w*\b|\b{pattern}\w*\s+{side_pattern}\b',text): result.add(side)
    return result


def apply_report_consistency(payload, *, today=None):
    if not getattr(get_settings(),'report_consistency_enabled',False): return payload
    today = today or datetime.now(ZoneInfo(cfg.CLINIC_TIMEZONE)).date()
    reports=[]
    for index, report in enumerate(payload.reports,1):
        reasons=codes(report.metadata.get('ingestion_reasons'))
        findings=concept_polarities_text(report.findings,clause_scoped=True)
        impression=concept_polarities_text(report.impression,clause_scoped=True)
        for concept in findings.keys() & impression.keys():
            if ('negative' in findings[concept] and 'positive_or_uncertain' in impression[concept]) or ('positive_or_uncertain' in findings[concept] and 'negative' in impression[concept]):
                reasons.append('report_findings_impression_conflict')
        for organ in cfg.ORGAN_TERMS:
            left,right=_sides(report.findings,organ),_sides(report.impression,organ)
            if left and right and not left.intersection(right): reasons.append('report_laterality_conflict')
        text=_fold(' '.join(part for part in (report.findings,report.impression,report.raw_text) if part))
        for organ in cfg.SEX_SPECIFIC_ORGANS.get(payload.clinical.sex,()):
            if re.search(rf'\b{_organ_pattern(organ)}\w*\b',text): reasons.append('report_patient_sex_mismatch')
        def day(field): return calendar_day(getattr(report,field,None) or report.metadata.get(field))
        if day('report_date') and day('report_date') > today: reasons.append('report_date_in_future')
        if any(day(before) and day(after) and day(before)>day(after) for before,after in cfg.REPORT_DATE_ORDER): reasons.append('report_date_order_conflict')
        if reasons:
            metadata={**report.metadata,'ingestion_reasons':list(dict.fromkeys(reasons)),'needs_review':True}
            if getattr(get_settings(),'consistency_section_enabled',False):
                metadata['consistency_flags']=[make_flag(code,metadata.get('source_file_name') or f'{report.report_type} #{index}',date=report.report_date,
                    page=metadata.get('source_page'),row=metadata.get('source_row')) for code in metadata['ingestion_reasons']]
            report=report.model_copy(update={'metadata':metadata})
        reports.append(report)
    return payload.model_copy(update={'reports':reports})
