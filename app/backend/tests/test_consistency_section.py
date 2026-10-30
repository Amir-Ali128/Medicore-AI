import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.config import Settings
from app.domain import simple_case_ai as ai
from app.domain.consistency_config import CONSISTENCY_HEADING, NO_INCONSISTENCY
from app.domain.consistency_flags import collect_consistency_flags
from app.schemas.simple_case import CaseAIInterpretationResponse, SimpleCaseRequest

HEADINGS = ('KLİNİK ÖZET','ÖNE ÇIKAN LABORATUVAR BULGULARI','TETKİK / RAPOR BULGULARI','ENTEGRE KLİNİK DEĞERLENDİRME',
            'OLASI KLİNİK DURUMLAR / AYIRICI TANI','ÖNERİLEN İLERİ TETKİK / İZLEM','SONUÇ / KANAAT','HEKİM NOTU')


def case(reasons=True):
    return SimpleCaseRequest(labs=[{'test_name':'Hb','value':10,'unit':'g/dL','event_date':'2026-10-01',
        'source_metadata':{'source_page':2,'source_row':4,'source_file_name':'test.pdf',
                           'ingestion_reasons':['numeric_value_conflict'] if reasons else [],
                           'document_warnings':['page_3:blurred_image'] if reasons else []}}])


@pytest.mark.parametrize('enabled', [False,True])
@pytest.mark.parametrize('has_warnings', [False,True])
def test_backend_section_is_guaranteed_and_false_preserves_wire_and_prompt(monkeypatch, enabled, has_warnings):
    payload = case(has_warnings); before = payload.model_dump(mode='json')
    text = '\n\n'.join(h+'\nKaynak metin.' for h in HEADINGS)
    create = AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text=text)]))
    monkeypatch.setattr(ai,'get_settings',lambda:SimpleNamespace(anthropic_api_key='fake',claude_hypothesis_model='test',
        claude_extraction_model=None,claude_vision_model=None,consistency_section_enabled=enabled))
    monkeypatch.setattr(ai,'AsyncAnthropic',lambda **kw:SimpleNamespace(messages=SimpleNamespace(create=create)))
    result=asyncio.run(ai.interpret_simple_case(payload))
    request=create.call_args.kwargs
    sent=json.loads(request['messages'][0]['content'][0]['text'])
    wire=CaseAIInterpretationResponse(report_text=result.report_text,model=result.model,consistency_flags=result.consistency_flags).model_dump()
    assert payload.model_dump(mode='json')==before
    assert create.call_count==1
    if enabled:
        assert result.report_text.startswith(CONSISTENCY_HEADING+'\n')
        assert sent['consistency_flags']==wire['consistency_flags']==collect_consistency_flags(payload)
        assert 'işaretli değerleri kesin kabul etme' in request['system']
        if not has_warnings: assert NO_INCONSISTENCY in result.report_text
        else: assert 'Sayfa 2 · Satır 4' in result.report_text
    else:
        assert result.report_text==text
        assert sent==ai._build_case_payload(payload)
        assert wire=={'report_text':text,'model':'test'}
        assert request['system']==ai._SYSTEM_PROMPT


def test_metadata_collection_handles_missing_unknown_codes_and_page_provenance():
    payload=case(); payload.labs.append(payload.labs[0].model_copy(deep=True))
    flags=collect_consistency_flags(payload)
    assert len(flags)==2
    assert flags[0]['source_page']==2 and flags[0]['source_row']==4
    assert flags[1]['source_page']==3 and flags[1]['parameter_or_report']=='test.pdf'
    assert collect_consistency_flags(SimpleCaseRequest())==[]
    payload.labs[0].source_metadata={'ingestion_reasons':'future_code'}
    assert 'ek denetim' in collect_consistency_flags(payload)[0]['message_tr']


def test_all_switches_default_false():
    settings=Settings(_env_file=None)
    assert all(getattr(settings,name) is False for name in ('consistency_section_enabled','lab_consistency_rules_enabled','report_consistency_enabled','lab_cross_read_enabled'))


def test_model_cannot_replace_or_duplicate_the_deterministic_section(monkeypatch):
    text=CONSISTENCY_HEADING+'\nMODELİN GÜVENSİZ BÖLÜMÜ\n'+'\n'.join(h+'\nKaynak.' for h in HEADINGS)
    create=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text=text)]))
    monkeypatch.setattr(ai,'get_settings',lambda:SimpleNamespace(anthropic_api_key='fake',claude_hypothesis_model='test',consistency_section_enabled=True))
    monkeypatch.setattr(ai,'AsyncAnthropic',lambda **kw:SimpleNamespace(messages=SimpleNamespace(create=create)))
    report=asyncio.run(ai.interpret_simple_case(case())).report_text
    assert report.count(CONSISTENCY_HEADING)==1
    assert 'MODELİN GÜVENSİZ BÖLÜMÜ' not in report
    assert 'numeric_value_conflict' in report
