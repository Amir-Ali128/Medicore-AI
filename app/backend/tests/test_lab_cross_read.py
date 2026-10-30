import asyncio
from copy import deepcopy
from datetime import datetime, UTC, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pymupdf
import pytest
from fastapi import UploadFile

from app.core import config
from app.domain import lab_document_ingestion as ingestion
from app.domain.lab_cross_read import cross_read_page, reconcile_readers, has_selectable_text
from app.domain.lab_document_ingestion import RawLabRow, validate_merge
from app.domain.canonical_lab_model import SourceContext
from app.domain.lab_document_normalizer import DocumentPage
from app.domain.lab_reader_usage import record_response_usage, reader_calls, summarize_calls
from app.domain.lab_reader_analytics import summarize_reader_events
from app.api.routes import simple_case


def row(value='2.1', **extra):
    return {'raw_parameter_name':'TSH','raw_value':value,'unit':'mIU/L','reference_min':0.27,'reference_max':4.2,'reference_text':'0.27 - 4.2','confidence':0.95,**extra}


def compare(a,b,unavailable=False):
    before=deepcopy((a,b))
    result=reconcile_readers(a,b,primary_name='Claude',secondary_name='OpenAI',unavailable=unavailable)
    assert (a,b)==before
    return result


@pytest.mark.parametrize('kind',['agreed','value','unit','reference','single','error'])
def test_required_cross_reader_scenarios(kind):
    a=[row()]; b=[row()]
    if kind=='value':b[0]['raw_value']='21'
    if kind=='unit':b[0]['unit']='IU/L'
    if kind=='reference':b[0]['reference_max']=5
    if kind in ('single','error'):b=[]
    result=compare(a,b,unavailable=kind=='error')
    expected={'agreed':'cross_read_agreed','value':'cross_read_value_conflict','unit':'cross_read_unit_or_reference_conflict','reference':'cross_read_unit_or_reference_conflict','single':'cross_read_single_reader_only','error':'cross_read_unavailable'}[kind]
    assert result[0]['cross_read_codes']==[expected]
    assert result[0]['raw_value']=='2.1'
    assert result[0]['reader_values']['Claude'][0]['raw_value']=='2.1'
    assert result[0]['reader_values']['OpenAI']==[] if not b else result[0]['reader_values']['OpenAI'][0]['raw_value']==b[0]['raw_value']
    assert result[0].get('needs_review',False)==(kind!='agreed')


def test_aliases_dates_unknowns_and_duplicates_preserve_all_observations():
    assert compare([row(raw_parameter_name='Glucose')],[row(raw_parameter_name='Glukoz')])[0]['cross_read_codes']==['cross_read_agreed']
    result=compare([row(event_date='2026-10-01')],[row(event_date='2026-10-02')])
    assert len(result)==2 and all(r['cross_read_codes']==['cross_read_single_reader_only'] for r in result)
    result=compare([row(),row('3')],[row('4')])
    assert len(result)==3 and [r['raw_value'] for r in result]==['2.1','3','4']
    assert compare([],[])==[]
    assert compare([row(raw_parameter_name='')],[row(raw_parameter_name='')])[0]['cross_read_codes']==['cross_read_single_reader_only']


def test_agreement_does_not_change_baseline_review_after_merge():
    for review in (False,True):
        a=[row(needs_review=review)]
        baseline=validate_merge([RawLabRow(a[0],1,1)],SourceContext('photo'))
        merged=compare(a,[row()]); raw=[RawLabRow(merged[0],1,1)]
        canonical=validate_merge(raw,SourceContext('photo'))
        from app.domain.lab_cross_read import restore_cross_read_metadata
        restored=restore_cross_read_metadata(canonical,raw)
        assert restored['labs'][0]['needs_review']==baseline['labs'][0]['needs_review']
        assert 'cross_read_agreed' in restored['labs'][0]['ingestion_reasons']
        assert restored['labs'][0]['reader_values']['OpenAI'][0]['raw_value']=='2.1'


def test_native_text_vs_scanned_pdf_routing():
    with pymupdf.open() as pdf:
        page=pdf.new_page(); blank=pdf.tobytes()
        page.insert_text((50,50),'TSH 2.1 mIU/L'); text=pdf.tobytes()
    assert has_selectable_text(DocumentPage(1,b'image',text))
    assert not has_selectable_text(DocumentPage(1,b'image',blank))
    assert not has_selectable_text(DocumentPage(1,b'image'))


@pytest.mark.parametrize('text_pdf',[False,True])
def test_two_readers_start_concurrently_and_keep_separate_counts(monkeypatch,text_pdf):
    from app.domain import lab_cross_read as cross
    monkeypatch.setattr(cross,'has_selectable_text',lambda page:text_pdf)
    async def scenario():
        started=set(); both=asyncio.Event()
        async def read(name,visible):
            started.add(name)
            if len(started)==2:both.set()
            await asyncio.wait_for(both.wait(),timeout=1)
            return {'labs':[row()],'visible_row_count':visible}
        result=await cross_read_page(DocumentPage(3,b'image'),local_reader=lambda:read('local',1),claude_reader=lambda:read('claude',2),openai_reader=lambda:read('openai',1))
        assert started==({'local','claude'} if text_pdf else {'claude','openai'})
        reports=result['reader_reports']
        assert [r['reader'] for r in reports]==(['local_parser','Claude'] if text_pdf else ['Claude','OpenAI'])
        assert any(r['row_count_check']=='mismatch' for r in reports)
        assert all(r['page']==3 and r['elapsed_ms']>=0 for r in reports)
    asyncio.run(scenario())


def test_reader_failure_preserves_other_and_both_failure_is_explicit():
    async def scenario():
        async def fail(): raise TimeoutError('secret patient details never echoed')
        good=AsyncMock(return_value={'labs':[row()],'visible_row_count':1})
        result=await cross_read_page(DocumentPage(1,b'image'),local_reader=fail,claude_reader=fail,openai_reader=good)
        assert result['labs'][0]['cross_read_codes']==['cross_read_unavailable']
        assert 'secret' not in str(result)
        assert result['reader_reports'][0]['available'] is False
        result=await cross_read_page(DocumentPage(1,b'image'),local_reader=fail,claude_reader=fail,openai_reader=fail)
        assert result['labs']==[] and len(result['extraction_errors'])>=2
    asyncio.run(scenario())


def test_openai_completeness_pass_independent_from_claude():
    async def scenario():
        claude=AsyncMock(return_value={'labs':[row()],'visible_row_count':1})
        openai=AsyncMock(side_effect=[{'labs':[row()],'visible_row_count':2},{'labs':[row(),row('3',raw_parameter_name='Hb')],'visible_row_count':2}])
        result=await cross_read_page(DocumentPage(1,b'image'),local_reader=None,claude_reader=claude,openai_reader=openai)
        assert claude.call_count==1 and openai.call_count==2
        assert [r['extracted_rows'] for r in result['reader_reports']]==[1,2]
        assert len(result['labs'])==2
    asyncio.run(scenario())


@pytest.mark.parametrize('enabled',[False,True])
def test_actual_upload_gate_metadata_and_rule_order(monkeypatch,enabled):
    from app.infrastructure.database import lab_reader_telemetry
    persist=AsyncMock()
    monkeypatch.setattr(lab_reader_telemetry,'persist_reader_event',persist)
    settings=SimpleNamespace(lab_cross_read_enabled=enabled,lab_consistency_rules_enabled=True,consistency_section_enabled=True)
    monkeypatch.setattr(simple_case,'get_settings',lambda:settings)
    monkeypatch.setattr(config,'get_settings',lambda:settings)
    monkeypatch.setattr(ingestion,'normalize_document',lambda *a,**kw:[DocumentPage(1,b'normalized')])
    claude=AsyncMock(return_value={'labs':[row('50')],'visible_row_count':1})
    openai=AsyncMock(return_value={'labs':[row('5')],'visible_row_count':1})
    monkeypatch.setattr(simple_case,'_extract_lab_document_with_claude',claude)
    monkeypatch.setattr(simple_case,'extract_lab_document_with_openai',openai)
    result=asyncio.run(simple_case._ingest_lab_upload(UploadFile(BytesIO(b'upload'),filename='lab.png'),'image/png'))
    assert claude.call_count==1 and openai.call_count==int(enabled)
    assert persist.call_count==2*int(enabled)
    metadata=result[0].source_metadata
    assert ('reader_values' in metadata) is enabled
    assert bool(metadata['page_reports'][0].get('reader_reports')) is enabled
    assert ('cross_read_value_conflict' in metadata['ingestion_reasons']) is enabled
    assert 'magnitude_suspect' in metadata['ingestion_reasons']
    assert result[0].value=='50'
    if enabled:
        assert metadata['reader_values']['OpenAI'][0]['raw_value']=='5'


def test_context_local_usage_pricing_and_unpriced_models():
    response=SimpleNamespace(usage=SimpleNamespace(input_tokens=100,output_tokens=20))
    calls=[]; token=reader_calls.set(calls)
    try:
        record_response_usage('Claude','claude-sonnet-5',response)
        record_response_usage('OpenAI','unknown-price',response)
    finally:reader_calls.reset(token)
    assert calls[0]['estimated_cost_usd']==0.0004
    assert calls[1]['estimated_cost_usd'] is None
    assert summarize_calls(calls)['estimated_cost_usd'] is None
    assert summarize_calls([],local=True)['estimated_cost_usd']==0
    record_response_usage('Claude','claude-sonnet-5',response)
    assert len(calls)==2


def test_saved_analytics_dedup_window_and_no_patient_text():
    now=datetime.now(UTC); cutoff=now-timedelta(minutes=1)
    event={'event_id':'one','recorded_at':now.isoformat(),'reader':'Claude','page':2,'elapsed_ms':4,'input_tokens':100,'output_tokens':20,'estimated_cost_usd':0.0004,'cost_status':'estimated','patient_name':'secret'}
    old={**event,'event_id':'old','recorded_at':(now-timedelta(days=1)).isoformat()}
    result=summarize_reader_events([{'lab_reader_usage':[event,old]},{'lab_reader_usage':[event]}],cutoff=cutoff,limit=10)
    assert result['page_reader_events']==1 and result['known_estimated_cost_usd']==0.0004
    assert 'secret' not in str(result)


@pytest.mark.parametrize('provider',['Claude','OpenAI'])
def test_real_provider_boundary_records_response_usage_without_extra_calls(monkeypatch,provider):
    import json
    async def scenario():
        response=SimpleNamespace(usage=SimpleNamespace(input_tokens=100,output_tokens=20),
            content=[SimpleNamespace(type='text',text=json.dumps({'values':[{'raw_parameter_name':'TSH','raw_value':'2.1'}],'visible_row_count':1}))],
            output_text=json.dumps({'labs':[row()],'visible_row_count':1}))
        create=AsyncMock(return_value=response)
        calls=[]; token=reader_calls.set(calls)
        try:
            if provider=='Claude':
                from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
                service=object.__new__(ClaudeLabExtractionService);service._model='claude-sonnet-5'
                service._client=SimpleNamespace(messages=SimpleNamespace(create=create))
                class Guard:
                    async def call(self,operation):return await operation()
                service._guard=Guard()
                await service.extract_from_bytes(b'image','lab.png','image/png')
            else:
                from app.domain import openai_lab_extraction_service as service
                monkeypatch.setattr(service,'get_settings',lambda:SimpleNamespace(openai_api_key='fake',openai_lab_model='unknown-price',lab_extraction_max_bytes=1000000))
                monkeypatch.setattr(service,'_client_for_key',lambda key:SimpleNamespace(responses=SimpleNamespace(create=create)))
                await service.extract_lab_document_with_openai(content=b'image',media_type='image/png',file_name='lab.png')
        finally:reader_calls.reset(token)
        assert create.call_count==1 and len(calls)==1
        assert calls[0]['input_tokens']==100 and calls[0]['output_tokens']==20
        assert calls[0]['provider']==provider
    asyncio.run(scenario())


@pytest.mark.parametrize('enabled',[False,True])
def test_anonymous_storage_and_schema_are_gated_and_no_patient_is_created(monkeypatch,enabled):
    from unittest.mock import MagicMock
    from uuid import uuid4
    from app.infrastructure.database import lab_reader_telemetry as telemetry
    settings=SimpleNamespace(lab_cross_read_enabled=enabled)
    monkeypatch.setattr(telemetry,'get_settings',lambda:settings)
    session=SimpleNamespace(add=MagicMock(),commit=AsyncMock())
    connection=SimpleNamespace(execute=AsyncMock())
    class Context:
        def __init__(self,value):self.value=value
        async def __aenter__(self):return self.value
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(telemetry,'AsyncSessionFactory',lambda:Context(session))
    engine=SimpleNamespace(begin=MagicMock(return_value=Context(connection)))
    event={'event_id':str(uuid4()),'recorded_at':datetime.now(UTC).isoformat(),'reader':'Claude','page':1,'estimated_cost_usd':None,'patient_name':'must-not-save'}
    async def scenario():
        await telemetry.ensure_lab_reader_events(engine)
        await telemetry.persist_reader_event(event)
    asyncio.run(scenario())
    assert session.add.call_count==int(enabled)
    assert engine.begin.call_count==int(enabled)
    if enabled:
        from app.infrastructure.database.models.lab_reader_event import LabReaderEvent
        saved=session.add.call_args.args[0]
        assert isinstance(saved,LabReaderEvent) and 'patient_name' not in saved.payload
        assert not LabReaderEvent.__table__.foreign_keys
        assert connection.execute.call_count==3 and session.commit.call_count==1


@pytest.mark.parametrize('enabled',[False,True])
def test_existing_admin_cost_analytics_includes_independent_reader_events_only_when_enabled(monkeypatch,enabled):
    from app.api.routes import ai_cost_analytics as analytics
    event={'event_id':'one','recorded_at':datetime.now(UTC).isoformat(),'reader':'Claude','estimated_cost_usd':0.002,'input_tokens':100,'output_tokens':40}
    aggregate=SimpleNamespace(mappings=lambda:SimpleNamespace(one=lambda:{}))
    rows=SimpleNamespace(mappings=lambda:SimpleNamespace(all=lambda:[]))
    readers=SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[event]))
    session=SimpleNamespace(execute=AsyncMock(side_effect=[aggregate,rows,readers]))
    class Context:
        async def __aenter__(self):return session
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(analytics,'AsyncSessionFactory',Context)
    monkeypatch.setattr(analytics,'get_settings',lambda:SimpleNamespace(lab_cross_read_enabled=enabled))
    result=asyncio.run(analytics.ai_costs(None,minutes=1440,limit=100))
    assert session.execute.call_count==2+int(enabled)
    assert ('lab_readers' in result) is enabled
    if enabled:
        assert result['lab_readers']['page_reader_events']==1
        assert result['lab_readers']['known_estimated_cost_usd']==0.002


def test_usage_sink_receives_failures_and_sink_failure_does_not_lose_rows():
    async def scenario():
        async def fail():raise TimeoutError()
        good=AsyncMock(return_value={'labs':[row()],'visible_row_count':1})
        sink=AsyncMock(side_effect=RuntimeError('do not expose raw database exception'))
        result=await cross_read_page(DocumentPage(1,b'image'),local_reader=fail,claude_reader=fail,openai_reader=good,usage_sink=sink)
        assert sink.call_count==2 and len(result['labs'])==1
        assert any(not call.args[0]['available'] for call in sink.call_args_list)
    asyncio.run(scenario())


@pytest.mark.parametrize('field',['raw_value','unit','reference_min','event_date'])
def test_missing_cross_read_cells_never_raise_or_rewrite_source(field):
    a=row();b=row();a.pop(field,None);b.pop(field,None)
    result=compare([a],[b])
    assert result[0].get(field)==a.get(field)
    if field in ('raw_value','unit'):assert 'cross_read_agreed' not in result[0]['cross_read_codes']


def test_cancelled_document_still_logs_each_started_reader_then_propagates_cancellation():
    async def scenario():
        started=set(); both=asyncio.Event(); blocked=asyncio.Event()
        async def read(name):
            started.add(name)
            if len(started)==2:both.set()
            await blocked.wait()
        sink=AsyncMock()
        task=asyncio.create_task(cross_read_page(DocumentPage(1,b'image'),local_reader=None,claude_reader=lambda:read('a'),openai_reader=lambda:read('b'),usage_sink=sink))
        await asyncio.wait_for(both.wait(),timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert sink.call_count==2
        assert all(not call.args[0]['available'] for call in sink.call_args_list)
    asyncio.run(scenario())


@pytest.mark.parametrize('enabled',[False,True])
def test_text_pdf_upload_never_short_circuits_second_reader_when_enabled(monkeypatch,enabled):
    from app.infrastructure.database import lab_reader_telemetry
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_text((50,50),'TSH 2.1 mIU/L');native=pdf.tobytes()
    settings=SimpleNamespace(lab_cross_read_enabled=enabled,consistency_section_enabled=False)
    monkeypatch.setattr(simple_case,'get_settings',lambda:settings)
    monkeypatch.setattr(config,'get_settings',lambda:settings)
    monkeypatch.setattr(ingestion,'normalize_document',lambda *a,**kw:[DocumentPage(1,b'normalized',native)])
    from unittest.mock import Mock
    local=Mock(return_value={'labs':[row()],'visible_row_count':1})
    claude=AsyncMock(return_value={'labs':[row()],'visible_row_count':1})
    openai=AsyncMock()
    monkeypatch.setattr(simple_case,'try_fast_pdf_lab_case',local)
    monkeypatch.setattr(simple_case,'_extract_lab_document_with_claude',claude)
    monkeypatch.setattr(simple_case,'extract_lab_document_with_openai',openai)
    monkeypatch.setattr(lab_reader_telemetry,'persist_reader_event',AsyncMock())
    result=asyncio.run(simple_case._ingest_lab_upload(UploadFile(BytesIO(native),filename='lab.pdf'),'application/pdf'))
    assert local.call_count==1 and claude.call_count==int(enabled) and openai.call_count==0
    assert result[0].value=='2.1'
    assert ('cross_read_agreed' in result[0].source_metadata['ingestion_reasons']) is enabled
