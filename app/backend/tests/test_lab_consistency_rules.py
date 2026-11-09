from copy import deepcopy
from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest

from app.core import config
from app.domain.lab_document_ingestion import apply_consistency_rules
from app.domain.lab_consistency_rules import annotate_request, annotate_request_with_database
from app.domain.consistency_config import DIFFERENTIAL_NAMES
from app.domain.lab_result_classification import classify_lab_result
from app.schemas.simple_case import SimpleCaseRequest


def row(name='Glucose', value=5, unit='mg/dL', low=None, high=None, flag=None, day='2026-10-01', **extra):
    return {'raw_parameter_name':name,'raw_value':str(value) if value is not None else None,'unit':unit,
            'reference_min':low,'reference_max':high,'source_flag':flag,'event_date':day,'ingestion_reasons':[], 'needs_review':False,**extra}


def run(monkeypatch, rows, enabled=True, **extra):
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(lab_consistency_rules_enabled=enabled,consistency_section_enabled=False))
    source={'labs':rows,**extra}; before=deepcopy(source)
    result=apply_consistency_rules(source)
    assert source==before
    for old,new in zip(source['labs'],result['labs']):
        assert {k:v for k,v in new.items() if k not in ('ingestion_reasons','needs_review')}=={k:v for k,v in old.items() if k not in ('ingestion_reasons','needs_review')}
    return result


def has(result, code): return any(code in row.get('ingestion_reasons',[]) for row in result['labs'])


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_source_flag_canonical_direction(monkeypatch,mode):
    item=row(value=20,low=1,high=10,flag='L' if mode=='positive' else 'H')
    if mode=='missing':item['status']='UNKNOWN'
    result=run(monkeypatch,[item])
    assert has(result,'source_flag_status_conflict')==(mode=='positive')


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_complete_differential_sum(monkeypatch,mode):
    values=[70,20,5,3,2] if mode!='positive' else [80,50,5,3,2]
    rows=[row(name+' %',value,'%') for name,value in zip(DIFFERENTIAL_NAMES,values)]
    if mode=='missing':rows.pop()
    assert has(run(monkeypatch,rows),'differential_sum_mismatch')==(mode=='positive')


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_absolute_percent_wbc_arithmetic(monkeypatch,mode):
    rows=[row('NEU',3 if mode=='positive' else 6,'10³/µL'),row('NEU%',60,'%'),row('WBC',10,'10^9/L')]
    if mode=='missing':rows.pop()
    assert has(run(monkeypatch,rows),'absolute_percent_mismatch')==(mode=='positive')


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_protein_sum(monkeypatch,mode):
    rows=[row('Total protein',9 if mode=='positive' else 7.2,'g/dL'),row('Albumin',4,'g/dL'),row('Globulin',3,'g/dL')]
    if mode=='missing':rows.pop()
    assert has(run(monkeypatch,rows),'protein_sum_mismatch')==(mode=='positive')


@pytest.mark.parametrize('code,value,flag',[('value_outside_reference_no_flag',20,None),('flag_without_reference_breach',5,'H'),('magnitude_suspect',101,None)])
@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_reference_checks(monkeypatch,code,value,flag,mode):
    item=row(value=value if mode!='negative' else 5,low=1,high=10,flag=flag if mode!='negative' else None)
    if mode=='missing':item['reference_min']=item['reference_max']=None
    assert has(run(monkeypatch,[item]),code)==(mode=='positive')


@pytest.mark.parametrize('mode',['positive','negative','missing'])
def test_database_reference_divergence(monkeypatch,mode):
    ranges={} if mode=='missing' else {'Glukoz':{'minimum':1 if mode=='positive' else 10,'maximum':10 if mode=='positive' else 100,'unit':'mg/dL'}}
    assert has(run(monkeypatch,[row(value=50,low=10,high=100)],database_ranges=ranges),'printed_reference_divergence')==(mode=='positive')


def test_false_is_exact_identity_even_with_all_conflicts(monkeypatch):
    result=run(monkeypatch,[row(value=1000,low=1,high=10,flag='L')],False)
    assert not result['labs'][0]['ingestion_reasons'] and result['labs'][0]['needs_review'] is False
    assert classify_lab_result(value=20,unit='mg/dL',reference_low=1,reference_high=10,ingestion_reasons=['source_flag_status_conflict']).status=='UNKNOWN'


def test_units_dates_and_derived_protein_are_conservative(monkeypatch):
    assert not has(run(monkeypatch,[row('NEU',3500,'cells/µL'),row('NEU%',50,'%'),row('WBC',7,'10^9/L')]),'absolute_percent_mismatch')
    rows=[row('Total protein',70,'g/L'),row('Albumin',4,'g/dL'),row('Globulin',3,'g/dL')]
    assert not has(run(monkeypatch,rows),'protein_sum_mismatch')
    rows[0]['raw_value']='100';rows[2]['is_derived']=True
    assert not has(run(monkeypatch,rows),'protein_sum_mismatch')
    unknown=[row('NEU',3,'unreadable'),row('NEU%',60,'%'),row('WBC',10,'10^9/L')]
    result=run(monkeypatch,unknown)
    assert has(result,'consistency_unit_unresolved') and not has(result,'absolute_percent_mismatch')
    unknown[0]['unit']='10^9/L'; unknown[2]['event_date']='2026-10-02'
    assert not has(run(monkeypatch,unknown),'absolute_percent_mismatch')
    for item in unknown:item['event_date']=None
    assert not has(run(monkeypatch,unknown),'absolute_percent_mismatch')


def test_annotations_do_not_change_canonical_classification_or_existing_reasons(monkeypatch):
    item=row(value=20,low=1,high=10,flag='L')
    result=run(monkeypatch,[item]); marked=result['labs'][0]
    cls=classify_lab_result(value=marked['raw_value'],unit=marked['unit'],reference_low=1,reference_high=10,ingestion_reasons=marked['ingestion_reasons'])
    assert cls.status=='HIGH'
    marked['ingestion_reasons'].append('numeric_value_conflict')
    assert classify_lab_result(value='20',unit='mg/dL',reference_low=1,reference_high=10,ingestion_reasons=marked['ingestion_reasons']).status=='UNKNOWN'
    assert apply_consistency_rules({'labs':None})=={'labs':None}


@pytest.mark.parametrize('enabled',[False,True])
def test_request_adapter_keeps_values_and_uses_the_real_reference_resolver_contract(monkeypatch,enabled):
    from app.domain import reference_resolver
    from app.infrastructure.database.repositories.clinical_parameter_repository import ClinicalParameterRepository
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(lab_consistency_rules_enabled=enabled,consistency_section_enabled=True))
    parameter=SimpleNamespace(id=uuid4(),canonical_name='Glukoz',parameter_code='GLUCOSE')
    catalog=AsyncMock(return_value=[parameter]); monkeypatch.setattr(ClinicalParameterRepository,'list_all',catalog)
    resolve=AsyncMock(return_value=SimpleNamespace(reference_min=1,reference_max=10,unit='mg/dL',needs_review=False))
    monkeypatch.setattr(reference_resolver.ReferenceResolver,'resolve',resolve)
    request=SimpleCaseRequest(clinical={'age':38,'sex':'male'},labs=[{'test_name':'Glucose','value':50,'unit':'mg/dL','source_reference':'10 - 100'}])
    before=request.model_dump()
    result=asyncio.run(annotate_request_with_database(request,object()))
    assert request.model_dump()==before and result.labs[0].value==request.labs[0].value
    if enabled:
        assert 'printed_reference_divergence' in result.labs[0].source_metadata['ingestion_reasons']
        assert resolve.call_args.args[0].extracted_reference_min is None
        assert resolve.call_args.args[0].patient_age==38
    else:
        assert result is request;catalog.assert_not_called();resolve.assert_not_called()
