import asyncio
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core import config
from app.domain import simple_case_ai as ai, report_consistency as rules
from app.domain.consistency_flags import collect_consistency_flags
from app.domain.report_consistency import apply_report_consistency
from app.domain.report_concepts import concept_polarities_text
from app.domain.radiology_provider_comparator import _concept_polarities
from app.schemas.simple_case import SimpleCaseRequest


def run(monkeypatch, report, sex='unknown', enabled=True):
    monkeypatch.setattr(rules,'get_settings',lambda:SimpleNamespace(report_consistency_enabled=enabled,consistency_section_enabled=True))
    payload=SimpleCaseRequest(clinical={'sex':sex},reports=[{'report_type':'US',**report}])
    before=payload.model_dump()
    result=apply_report_consistency(payload,today=date(2026,10,30))
    assert payload.model_dump()==before
    assert result.reports[0].model_dump(exclude={'metadata'})==payload.reports[0].model_dump(exclude={'metadata'})
    return result


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_findings_impression_polarity(monkeypatch,mode):
    result=run(monkeypatch,{'findings':'Hidronefroz yok.','impression':{'positive':'Hidronefroz vardır.','negative':'Hidronefroz izlenmiyor.','missing':None}[mode]})
    assert ('report_findings_impression_conflict' in result.reports[0].metadata.get('ingestion_reasons',[]))==(mode=='positive')


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_laterality_same_organ(monkeypatch,mode):
    result=run(monkeypatch,{'findings':'Sağ böbrekte taş.','impression':{'positive':'Sol böbrekte taş.','negative':'Sağ böbrekte taş. Sol akciğer normal.','missing':None}[mode]})
    assert ('report_laterality_conflict' in result.reports[0].metadata.get('ingestion_reasons',[]))==(mode=='positive')


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_recorded_sex_organ(monkeypatch,mode):
    result=run(monkeypatch,{'findings':'Prostat boyutu normal.'},sex={'positive':'female','negative':'male','missing':'unknown'}[mode])
    flags=collect_consistency_flags(result)
    assert any(f['code']=='report_patient_sex_mismatch' for f in flags)==(mode=='positive')
    if mode=='positive': assert flags[0]['severity']=='high'


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_future_report_date(monkeypatch,mode):
    result=run(monkeypatch,{'report_date':{'positive':'2026-10-31','negative':'2026-10-30','missing':None}[mode]})
    assert ('report_date_in_future' in result.reports[0].metadata.get('ingestion_reasons',[]))==(mode=='positive')


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_date_order(monkeypatch,mode):
    result=run(monkeypatch,{'report_date':'2026-10-20','exam_date':{'positive':'2026-10-21','negative':'2026-10-19','missing':None}[mode]})
    assert ('report_date_order_conflict' in result.reports[0].metadata.get('ingestion_reasons',[]))==(mode=='positive')


def test_switch_off_and_idempotent_annotations(monkeypatch):
    report={'findings':'Sağ böbrek hidronefroz yok.','impression':'Sol böbrek hidronefroz vardır.', 'metadata':{'source_page':2,'source_row':3,'ingestion_reasons':['existing']}}
    result=run(monkeypatch,report,enabled=False)
    assert result.reports[0].metadata==report['metadata']
    result=run(monkeypatch,report)
    twice=apply_report_consistency(result,today=date(2026,10,30))
    assert result==twice
    flags=collect_consistency_flags(result)
    assert any(f['source_page']==2 and f['source_row']==3 for f in flags)


def test_clause_scoping_bilateral_and_timezone(monkeypatch):
    assert concept_polarities_text('Hidronefroz yok. Kalsifikasyon vardır.',clause_scoped=True)=={'hydronephrosis':{'negative'},'calcification':{'positive_or_uncertain'}}
    result=run(monkeypatch,{'findings':'Sağ böbrek normal. Sol böbrek normal.','impression':'Sol böbrek normal.',
                           'exam_date':'2026-10-20T23:30:00Z','report_date':'2026-10-21T03:00:00+03:00'})
    assert not result.reports[0].metadata.get('ingestion_reasons')


def test_legacy_comparator_window_and_negation_unchanged():
    for text, expected in [('Hidronefroz yok.',{'negative'}),('Hidronefroz vardır.',{'positive_or_uncertain'}),('Hidronefroz yokluk değil.',{'negative'}),('Hidronefroz boyok.',{'positive_or_uncertain'})]:
        review=SimpleNamespace(summary=text,observations=[])
        assert _concept_polarities(review)['hydronephrosis']==expected


@pytest.mark.parametrize('enabled',[False,True])
def test_report_flags_reach_llm_and_backend_section(monkeypatch,enabled):
    from tests.test_consistency_section import HEADINGS
    settings=SimpleNamespace(report_consistency_enabled=enabled,consistency_section_enabled=True,anthropic_api_key='fake',claude_hypothesis_model='test')
    monkeypatch.setattr(rules,'get_settings',lambda:settings)
    monkeypatch.setattr(ai,'get_settings',lambda:settings)
    create=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='\n'.join(h+'\nKaynak.' for h in HEADINGS))]))
    monkeypatch.setattr(ai,'AsyncAnthropic',lambda **kw:SimpleNamespace(messages=SimpleNamespace(create=create)))
    payload=SimpleCaseRequest(reports=[{'report_type':'US','findings':'Hidronefroz yok.','impression':'Hidronefroz vardır.'}])
    result=asyncio.run(ai.interpret_simple_case(payload))
    sent=json.loads(create.call_args.kwargs['messages'][0]['content'][0]['text'])
    assert bool(sent['consistency_flags']) is enabled
    assert ('report_findings_impression_conflict' in result.report_text) is enabled
    assert create.call_count==1
