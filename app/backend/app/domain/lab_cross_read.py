"""Independent page readers. A is display provenance, never a correctness vote."""

from app.domain.privacy_gateway import PrivacyViolation
import asyncio
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from datetime import datetime, UTC
import logging
from time import perf_counter
from uuid import uuid4

from app.domain import consistency_config as cfg
from app.domain.alias_engine import curated_consistency_name, normalize_alias
from app.domain.document_dates import calendar_day
from app.domain.lab_document_errors import reader_failure
from app.domain.lab_reader_usage import reader_calls, summarize_calls
from app.domain.lab_result_classification import normalize_lab_unit

logger=logging.getLogger(__name__)


def has_selectable_text(page):
    if page.native_pdf is None: return False
    import pymupdf
    try:
        with pymupdf.open(stream=page.native_pdf,filetype='pdf') as document:
            return any(p.get_text().strip() for p in document)
    except (RuntimeError, ValueError): return False


def _name(row):
    raw=row.get('raw_parameter_name') or row.get('test_name') or row.get('canonical_name') or ''
    return curated_consistency_name(raw,row.get('unit')) or (normalize_alias(raw)+(' %' if '%' in raw or row.get('unit')=='%' else ''))


def _key(row):
    days=tuple(str(calendar_day(row.get(field)) or row.get(field) or '') for field in cfg.CROSS_READ_DATE_FIELDS)
    return _name(row),days


def _scalar(value):
    if value is None or value=='': return None
    try:
        numeric=Decimal(str(value).strip().replace(',','.'))
        return numeric if numeric.is_finite() else str(value).strip()
    except InvalidOperation: return str(value).strip()


def _value(row):
    return _scalar(row.get('raw_value') if row.get('raw_value') not in (None,'') else row.get('normalized_value',row.get('value')))


def _reference(row):
    lo,hi=row.get('reference_min'),row.get('reference_max')
    if lo is not None or hi is not None: return (_scalar(lo),_scalar(hi),normalize_lab_unit(row.get('reference_unit') or row.get('unit')))
    return (str(row.get('reference_text') or '').strip().replace(',','.'),normalize_lab_unit(row.get('reference_unit') or row.get('unit')))


def reconcile_readers(primary, secondary, *, primary_name, secondary_name, unavailable=False):
    """Retain A rows and B-only rows, preserving every contradictory observation."""
    a=deepcopy(primary or []); b=deepcopy(secondary or []); result=[]; used=set()
    agroups={}; bgroups={}
    for i,row in enumerate(a): agroups.setdefault(_key(row),[]).append(i)
    for i,row in enumerate(b): bgroups.setdefault(_key(row),[]).append(i)
    def output(row, left, right, codes):
        row['reader_values']={primary_name:[{k:v for k,v in item.items() if k in cfg.CROSS_READ_VALUE_FIELDS} for item in left],
                              secondary_name:[{k:v for k,v in item.items() if k in cfg.CROSS_READ_VALUE_FIELDS} for item in right]}
        # Append agreement after validate_merge so an informational code cannot turn review on.
        row['cross_read_codes']=codes
        active=[code for code in codes if code!='cross_read_agreed']
        row['ingestion_reasons']=list(dict.fromkeys([*(row.get('ingestion_reasons') or []),*active]))
        if active: row['needs_review']=True
        result.append(row)
    for row in a:
        key=_key(row); matches=bgroups.get(key,[])
        if not _name(row) or len(agroups[key])!=1 or len(matches)!=1:
            output(row,[a[i] for i in agroups[key]],[b[i] for i in matches],['cross_read_unavailable' if unavailable else 'cross_read_single_reader_only'])
            continue
        j=matches[0]; other=b[j]; used.add(j); codes=[]
        left_value, right_value = _value(row), _value(other)
        if left_value is not None and right_value is not None and left_value!=right_value: codes.append('cross_read_value_conflict')
        if normalize_lab_unit(row.get('unit'))!=normalize_lab_unit(other.get('unit')) or _reference(row)!=_reference(other): codes.append('cross_read_unit_or_reference_conflict')
        complete = left_value is not None and right_value is not None and bool(row.get('unit')) and bool(other.get('unit'))
        output(row,[row],[other],codes or (['cross_read_agreed'] if complete else []))
    for j,row in enumerate(b):
        if j not in used:
            output(row,[a[i] for i in agroups.get(_key(row),[])],[row],['cross_read_unavailable' if unavailable else 'cross_read_single_reader_only'])
    return result


def _count(result):
    count=result.get('visible_row_count')
    return count if isinstance(count,int) and not isinstance(count,bool) and count>=0 else None


async def cross_read_page(page, *, local_reader, claude_reader, openai_reader, usage_sink=None):
    text_pdf=await asyncio.to_thread(has_selectable_text,page)
    readers=[('local_parser',local_reader),('Claude',claude_reader)] if text_pdf else [('Claude',claude_reader),('OpenAI',openai_reader)]
    async def read(name,reader):
        started=perf_counter(); calls=[]; token=reader_calls.set(calls); result={}; errors=[]; cancelled=None
        try:
            result=await asyncio.wait_for(reader(),timeout=cfg.CROSS_READ_TIMEOUT_SECONDS) or {}
            if not isinstance(result,dict): result={}
            # Claude already audits completeness inside its existing service. OpenAI gets its own bounded audit.
            for _ in range(cfg.CROSS_READ_COMPLETENESS_RETRY_LIMIT if name=='OpenAI' else 0):
                expected=_count(result); rows=result.get('labs') or []
                if not (expected is not None and expected!=len(rows) or expected is None and len(rows)<=cfg.CROSS_READ_SMALL_TABLE_ROWS): break
                try:
                    audit=await asyncio.wait_for(reader(),timeout=max(cfg.CROSS_READ_MIN_REMAINING_SECONDS,cfg.CROSS_READ_TIMEOUT_SECONDS-(perf_counter()-started))) or {}
                    existing=list(rows)
                    for row in audit.get('labs') or []:
                        if row not in existing: existing.append(row)
                    counts=[n for n in (_count(result),_count(audit)) if n is not None]
                    result={**result,'labs':existing,'visible_row_count':max(counts) if counts else None,
                            'warnings':[*result.get('warnings',[]),*audit.get('warnings',[])],
                            'extraction_errors':[*result.get('extraction_errors',[]),*audit.get('extraction_errors',[])]}
                except PrivacyViolation:
                    raise
                except Exception as exc:
                    errors.append(reader_failure(name,exc)); result={**result,'warnings':[*result.get('warnings',[]),'image_completeness_audit_failed']}
        except asyncio.CancelledError as exc:
            cancelled=exc
            errors.append(reader_failure(name,TimeoutError()))
        except PrivacyViolation:
            raise
        except Exception as exc: errors.append(reader_failure(name,exc))
        finally: reader_calls.reset(token)
        values=[row for row in (result.get('labs') or []) if isinstance(row,dict)]
        expected=_count(result); warnings=list(result.get('warnings',[]))
        if expected is None: warnings.append('visible_row_count_unverified')
        elif expected!=len(values): warnings.append('visible_row_count_mismatch')
        errors.extend(result.get('extraction_errors',[]))
        if not values and not errors: errors.append({'reader':name,'code':'no_rows','message':f'{name}: laboratuvar satırı okunamadı.'})
        report={'event_id':str(uuid4()),'reader':name,'page':page.number,'recorded_at':datetime.now(UTC).isoformat(),'elapsed_ms':round((perf_counter()-started)*1000,2),
                'extracted_rows':len(values),'visible_rows':expected,'row_count_check':'unknown' if expected is None else 'matched' if expected==len(values) else 'mismatch',
                'warnings':list(dict.fromkeys(warnings)),'extraction_errors':errors,'available':bool(values),**summarize_calls(calls,local=name=='local_parser')}
        logger.info('lab_cross_read reader=%s page=%s elapsed_ms=%s estimated_cost_usd=%s cost_status=%s',name,page.number,report['elapsed_ms'],report['estimated_cost_usd'],report['cost_status'])
        if usage_sink is not None:
            try:
                await asyncio.wait_for(usage_sink(report),timeout=cfg.READER_ANALYTICS_WRITE_TIMEOUT_SECONDS)
            except PrivacyViolation:
                raise
            except Exception:
                logger.warning('lab_reader_analytics_write_failed event_id=%s reader=%s page=%s',report['event_id'],name,page.number)
        if cancelled is not None: raise cancelled
        return values,report
    (a,ar),(b,br)=await asyncio.gather(*(read(name,reader) for name,reader in readers))
    unavailable=not a or not b
    rows=reconcile_readers(a,b,primary_name=readers[0][0],secondary_name=readers[1][0],unavailable=unavailable)
    return {'labs':rows,'visible_row_count':None,'reader_reports':[ar,br],
            'warnings':list(dict.fromkeys([*ar['warnings'],*br['warnings'],*(['cross_read_unavailable'] if unavailable else [])])),
            'extraction_errors':[*ar['extraction_errors'],*br['extraction_errors']]}


def restore_cross_read_metadata(case, raw_rows):
    original={(raw.source_page,raw.source_row):raw.data for raw in raw_rows}
    for row in case['labs']:
        snapshots=[]; codes=list(row.get('ingestion_reasons',[]))
        for location in row['source_locations']:
            raw=original.get((location['page'],location['row']),{})
            if raw.get('reader_values') is not None: snapshots.append(raw['reader_values'])
            codes.extend(raw.get('cross_read_codes',[]))
        if snapshots:
            row['reader_values']=snapshots[0] if len(snapshots)==1 else {'observations':snapshots}
            row['ingestion_reasons']=list(dict.fromkeys(codes))
    return case
