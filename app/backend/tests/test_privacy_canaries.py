"""Synthetic canaries at every real provider call site; SDKs never use the network."""
import asyncio
import ast
import base64
from datetime import date
import importlib
import io
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pymupdf
from PIL import Image

from app.domain import privacy_gateway as gateway
from app.domain.privacy_gateway import PrivacyViolation
from app.infrastructure.ai_privacy_client import PrivacyContext,context,privacy_call,private_media
from tests.test_privacy_gateway import NAME,fake_tckn,synthetic_image,synthetic_pdf,fake_tokens

SITES=(
 'claude_lab_extraction_service','openai_lab_extraction_service','openai_case_document_service',
 'scanned_medical_report_pdf_ai','report_document_image_ai','radiology_image_ai',
 'openai_radiology_second_reader','gemini_radiology_third_reader','claude_clinical_hypothesis_service',
 'simple_case_ai','source_only_case_evaluation','medical_report_summary_ai','openai_lab_clinical_service',
)
# 13 modules / 14 calls: simple_case_ai's bounded retry shares its one guarded call.
CANARY=f'Hasta Adı: {NAME}\nTCKN: {fake_tckn()}\nE-posta: sentetik@example.invalid\nHemoglobin 13.2 g/dL'


class Sent(BaseException):pass


@pytest.fixture
def safe_ocr(monkeypatch):
    def ocr(image, **kwargs):
        scale=image.width/1000
        tokens=fake_tokens(image)
        if image.width != 1000:
            from app.domain.local_ocr_lab_parser import OcrToken
            tokens=[OcrToken(t.text,t.score,t.x*scale,t.y*scale,t.width*scale,t.height*scale) for t in tokens]
        return tokens[1:] if max(image.getpixel((int(200*scale),int(50*scale))))<10 else tokens
    monkeypatch.setattr(gateway,'_ocr_tokens',ocr)


def flow(monkeypatch, site, capture):
    module=importlib.import_module('app.domain.'+site)
    settings=NS(anthropic_api_key='fake',openai_api_key='fake',gemini_api_key='fake',
        claude_hypothesis_model='test',claude_extraction_model='test',claude_vision_model='test',
        openai_lab_model='test',openai_vision_model='test',openai_lab_clinical_model='test',
        gemini_vision_model='test',gemini_radiology_model='test',lab_extraction_max_bytes=25_000_000,
        ai_call_timeout_seconds=2,lab_document_read_timeout_seconds=2,gemini_radiology_enabled=True,
        openai_radiology_second_reader_enabled=True,gemini_radiology_third_reader_enabled=True)
    if hasattr(module,'get_settings'):monkeypatch.setattr(module,'get_settings',lambda:settings)
    async def create(**kwargs):capture.append(kwargs);raise Sent()
    client=NS(messages=NS(create=create),responses=NS(create=create),interactions=NS(create=create))
    for name in ('AsyncAnthropic','AsyncOpenAI','_client_for_key'):
        if hasattr(module,name):monkeypatch.setattr(module,name,lambda *a,**kw:client)
    class Aio:
        async def __aenter__(self):return client
        async def __aexit__(self,*args):pass
    if hasattr(module,'genai'):monkeypatch.setattr(module.genai,'Client',lambda **kw:NS(aio=Aio()))
    class Guard:
        async def call(self,operation):return await operation()
    if hasattr(module,'get_anthropic_guard'):monkeypatch.setattr(module,'get_anthropic_guard',lambda *a,**kw:Guard())
    image=synthetic_image();pdf=synthetic_pdf()
    if site=='claude_lab_extraction_service':
        service=object.__new__(module.ClaudeLabExtractionService);service._model='test';service._client=client;service._guard=Guard()
        return service.extract_from_bytes(pdf,NAME+'.pdf','application/pdf')
    if site=='openai_lab_extraction_service':return module.extract_lab_document_with_openai(content=pdf,media_type='application/pdf',file_name=NAME+'.pdf')
    if site=='openai_case_document_service':return module.extract_case_documents_with_openai(documents=[(image,'image/png',NAME+'.png')])
    if site=='scanned_medical_report_pdf_ai':return module.extract_scanned_medical_report_pdf(content=pdf,file_name=NAME+'.pdf')
    if site in ('report_document_image_ai','radiology_image_ai','openai_radiology_second_reader','gemini_radiology_third_reader'):
        function={'report_document_image_ai':'review_radiology_media','radiology_image_ai':'review_radiology_image',
                  'openai_radiology_second_reader':'review_radiology_media_openai','gemini_radiology_third_reader':'review_radiology_media_gemini'}[site]
        return getattr(module,function)(content=image,media_type='image/png',modality='XRAY')
    if site=='simple_case_ai':
        from app.schemas.simple_case import SimpleCaseRequest
        return module.interpret_simple_case(SimpleCaseRequest(clinical={'notes':CANARY,'age':46}))
    if site=='medical_report_summary_ai':return module.summarize_medical_report_text(CANARY)
    if site=='openai_lab_clinical_service':return module.synthesize_lab_clinical_assessment(rows=[{'canonical_name':CANARY,'raw_value':'13.2','unit':'g/dL'}],derived_metrics=[],patient_age=46,patient_sex='female')
    from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService
    from app.schemas.clinical_copilot import ClinicalHypothesisGenerationRequest
    service=object.__new__(ClaudeClinicalHypothesisService);service._client=client;service._model='test'
    service._runs=NS(get_by_id=AsyncMock(return_value=NS(patient_id=uuid4())))
    service._lab_results=NS(list_for_analysis_run=AsyncMock(return_value=[object()]))
    service._review_results=lambda results,request:results
    service._lab_flags=lambda results:['REVIEW']
    service._dedupe=lambda values:list(dict.fromkeys(values))
    request=ClinicalHypothesisGenerationRequest(metadata_json={'symptoms':[CANARY],'source_summaries':{'clinical':CANARY}})
    if site=='source_only_case_evaluation':return module.generate_source_only_case(service,uuid4(),request)
    return service.generate_for_analysis_run(uuid4(),request)


def check_request(value):
    if isinstance(value,dict):
        for item in value.values():check_request(item)
    elif isinstance(value,list):
        for item in value:check_request(item)
    elif isinstance(value,str):
        gateway.final_leak_check(value,[NAME,fake_tckn(),'sentetik@example.invalid'])
        if value.startswith('data:'):
            media,encoded=value.split(',',1);check_binary(base64.b64decode(encoded))
        elif len(value)>100:
            try:binary=base64.b64decode(value,validate=True)
            except ValueError:return
            if binary.startswith((b'%PDF',b'\x89PNG',b'\xff\xd8')):check_binary(binary)


def check_binary(data):
    if data.startswith(b'%PDF'):
        gateway.final_leak_check(data,[NAME,fake_tckn()])
        with pymupdf.open(stream=data,filetype='pdf') as pdf:
            assert 'Hemoglobin 13.2 g/dL' in ''.join(page.get_text() for page in pdf)
    else:
        with Image.open(io.BytesIO(data)) as image:
            assert not image.getexif()
            assert max(image.getpixel((200,50)))<10


@pytest.mark.parametrize('site',SITES)
def test_each_real_call_site_has_no_identifier_in_captured_request(monkeypatch,safe_ocr,site):
    captured=[]
    async def scenario():
        token=context.set(PrivacyContext(str(uuid4()),(NAME,fake_tckn(),'sentetik@example.invalid'),46))
        try:
            with pytest.raises(Sent):await flow(monkeypatch,site,captured)
        finally:context.reset(token)
    asyncio.run(scenario())
    assert len(captured)==1
    check_request(captured[0])


@pytest.mark.parametrize('site',SITES[:8])
def test_binary_call_sites_block_ocr_failure_before_any_sdk_call(monkeypatch,site):
    captured=[]
    def unavailable(*args):raise PrivacyViolation()
    monkeypatch.setattr(gateway,'_ocr_tokens',unavailable)
    # Text PDF sites need an actual scanned page to exercise the OCR failure path.
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_image(page.rect,stream=synthetic_image());scanned=pdf.tobytes()
    monkeypatch.setattr(__import__(__name__,fromlist=['synthetic_pdf']),'synthetic_pdf',lambda:scanned)
    with pytest.raises(PrivacyViolation):asyncio.run(flow(monkeypatch,site,captured))
    assert captured==[]


def test_audit_is_safe_and_failed_call_is_blocked(caplog):
    async def scenario():
        client=AsyncMock()
        await privacy_call(client,provider='test',call_site='synthetic',input=CANARY)
        with pytest.raises(PrivacyViolation):await privacy_call(client,provider='test',call_site='synthetic',input=b'raw bytes')
        assert client.call_count==1
    asyncio.run(scenario())
    logs='\n'.join(record.message for record in caplog.records if 'ai_privacy_audit' in record.message)
    for secret in (NAME,fake_tckn(),'sentetik@example.invalid'):assert secret not in logs
    assert '"blocked": true' in logs and 'redaction_counts' in logs


def test_ast_guard_has_no_unprotected_sdk_calls_or_binary_encoding():
    root=Path(__file__).parents[1]/'app'
    violations=[];calls=0
    for folder in ('domain','api'):
        for path in (root/folder).rglob('*.py'):
            source=path.read_text(encoding='utf-8-sig')
            tree=ast.parse(source)
            # The sole non-AI HTTP client is opt-in visitor geolocation, not patient/AI transport.
            for import_node in ast.walk(tree):
                if isinstance(import_node,ast.ImportFrom) and import_node.module in ('base64','httpx','requests') and path.name!='analytics.py':
                    violations.append(f'{path}: unapproved encoder/HTTP import')
                if isinstance(import_node,ast.Import) and any(alias.name in ('httpx','requests') for alias in import_node.names) and path.name!='analytics.py':
                    violations.append(f'{path}: unapproved HTTP transport')
            parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if not isinstance(node,ast.Call):continue
                if isinstance(node.func,ast.Attribute) and 'b64encode' in node.func.attr:violations.append(str(path))
                if isinstance(node.func,ast.Name) and node.func.id=='privacy_call':calls+=1
                if isinstance(node.func,ast.Attribute) and node.func.attr in ('create','parse','stream','generate_content','generate_content_stream'):
                    target=ast.unparse(node.func)
                    if any(name in target for name in ('.messages.','.responses.','.interactions.','.completions.','generate_content')):
                        # An SDK method may be passed as a callable, never invoked directly.
                        violations.append(f'{path}:{node.lineno}')
            # Existing usage proxy is a pure forwarder of the already-sanitized kwargs.
            if path.name=='claude_usage_runtime.py':
                assert 'self._messages.create(*args, **kwargs)' in path.read_text()
    assert not violations,violations
    assert calls==13


def test_db_identifiers_birth_age_and_context_isolation():
    from app.infrastructure.ai_privacy_context import load_patient_identifiers
    from app.infrastructure.ai_privacy_client import context
    async def scenario():
        one,two=uuid4(),uuid4()
        patients={one:NS(date_of_birth=date(1980,2,1),protocol_no='SYN-001',external_ref=None,
                        metadata_json={'identity':{'full_name':NAME,'tckn':fake_tckn(),'phone':'05550000000','email':'sentetik@example.invalid','address':'Sentetik Sokak 12'}}),
                  two:NS(date_of_birth=None,protocol_no='SYN-002',external_ref=None,metadata_json={'full_name':'Deneme Soyadı'})}
        session=NS(get=AsyncMock(side_effect=lambda model,key:patients[key]))
        first=await load_patient_identifiers(session,one)
        assert NAME in first.known_identifiers and '01.02.1980' in first.known_identifiers
        assert first.patient_id==str(one) and first.age is not None
        captured=[]; ready=asyncio.Event(); started=[]
        async def send(patient_id, text):
            privacy=await load_patient_identifiers(session,patient_id);token=context.set(privacy)
            try:
                started.append(patient_id)
                if len(started)==2:ready.set()
                await ready.wait()
                async def sdk(**kw):captured.append((context.get().patient_id,kw))
                await privacy_call(sdk,provider='test',call_site='synthetic',input=text)
            finally:context.reset(token)
        await asyncio.gather(send(one,NAME),send(two,'Deneme Soyadı'))
        assert {key for key,data in captured}=={str(one),str(two)}
        assert all('[HASTA_ADI]' in item['input'] for key,item in captured)
        assert context.get().patient_id is None
    asyncio.run(scenario())


def test_actual_fastapi_dependency_and_privacy_error_handler_prevent_send(monkeypatch):
    from fastapi import FastAPI,Depends
    from fastapi.testclient import TestClient
    from app.api.dependencies import get_session
    from app.infrastructure.ai_privacy_context import privacy_request_context
    from app.main import privacy_failure
    patient_id=uuid4();sdk=AsyncMock()
    session=NS(get=AsyncMock(return_value=NS(date_of_birth=None,protocol_no='SYN-001',external_ref=None,metadata_json={'full_name':NAME})))
    async def fake_session():yield session
    app=FastAPI(dependencies=[Depends(privacy_request_context)])
    app.dependency_overrides[get_session]=fake_session
    app.add_exception_handler(PrivacyViolation,privacy_failure)
    @app.post('/check/{patient_id}')
    async def check(patient_id:str):
        await privacy_call(sdk,provider='test',call_site='synthetic',input=private_media(b'invalid image','image/png'))
    @app.post('/text/{patient_id}')
    async def text(patient_id:str):
        await privacy_call(sdk,provider='test',call_site='synthetic',input=NAME)
        return {'ok':True}
    @app.post('/noop/{patient_id}')
    async def noop(patient_id:str):return {'ok':True}
    client=TestClient(app)
    assert client.post('/noop/'+str(patient_id)).status_code==200
    session.get.assert_not_called()
    response=client.post('/check/'+str(patient_id))
    assert response.status_code==422
    assert response.json()['code']=='PRIVACY_REDACTION_FAILED'
    assert response.json()['detail']==gateway.PRIVACY_MESSAGE
    assert sdk.call_count==0 and context.get().patient_id is None
    assert client.post('/text/'+str(patient_id)).status_code==200
    assert sdk.call_args.kwargs['input']=='[HASTA_ADI]'
    assert context.get().patient_id is None


def test_untrusted_nested_schema_and_raw_urls_cannot_bypass_sanitization():
    async def scenario():
        sdk=AsyncMock()
        token=context.set(PrivacyContext(None,(NAME,)))
        try:
            await privacy_call(sdk,provider='test',call_site='synthetic',input=json.dumps({'schema':{'patient_name':NAME},'date_of_birth':'1980-02-01','age':46}))
            assert NAME not in sdk.call_args.kwargs['input'] and '1980-02-01' not in sdk.call_args.kwargs['input']
            for value in ('https://example.invalid/private.png','data:image/png;base64,aW52YWxpZA=='):
                with pytest.raises(PrivacyViolation):await privacy_call(sdk,provider='test',call_site='synthetic',input=[{'image_url':value}])
            assert sdk.call_count==1
        finally:context.reset(token)
    asyncio.run(scenario())


def test_birth_date_becomes_age_but_absolute_trend_dates_and_test_names_survive():
    async def scenario():
        sdk=AsyncMock()
        await privacy_call(sdk,provider='test',call_site='synthetic',input=json.dumps({
            'date_of_birth':'01.02.1980','event_date':'2026-10-02','report_date':'2026-10-04',
            'labs':[{'name':'Hemoglobin','value':13.2,'unit':'g/dL','reference':'12 - 16'}]}))
        payload=json.loads(sdk.call_args.kwargs['input'])
        assert 'date_of_birth' not in payload and isinstance(payload['age'],int)
        assert payload['event_date']=='2026-10-02' and payload['report_date']=='2026-10-04'
        assert payload['labs'][0]=={'name':'Hemoglobin','value':13.2,'unit':'g/dL','reference':'12 - 16'}
    asyncio.run(scenario())


def test_final_transport_check_covers_keys_and_numeric_canaries():
    async def scenario():
        sdk=AsyncMock()
        await privacy_call(sdk,provider='test',call_site='synthetic',input={'unlabelled_number':int(fake_tckn())})
        assert sdk.call_args.kwargs['input']['unlabelled_number']=='[TCKN]'
        token=context.set(PrivacyContext(None,(NAME,)))
        try:
            with pytest.raises(PrivacyViolation):await privacy_call(sdk,provider='test',call_site='synthetic',input={NAME:'canary in a key'})
        finally:context.reset(token)
        assert sdk.call_count==1
    asyncio.run(scenario())


def test_retry_prompt_json_prefix_with_escaped_linebreak_names_is_sanitized():
    async def scenario():
        sdk=AsyncMock();token=context.set(PrivacyContext(None,(NAME,)))
        try:
            retry=json.dumps({'clinical':{'notes':'AYSE\nYILMAZOGLU'}},ensure_ascii=True)+'\n\nBaşlıkları tamamla.'
            await privacy_call(sdk,provider='test',call_site='retry',input=retry)
            captured=sdk.call_args.kwargs['input']
            assert 'YILMAZOGLU' not in captured and 'AYSE' not in captured
            assert captured.endswith('Başlıkları tamamla.')
        finally:context.reset(token)
    asyncio.run(scenario())
