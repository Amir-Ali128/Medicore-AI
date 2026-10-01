"""Simple case normalization, access control and report freshness regressions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dependencies
from app.api.routes import auth, lab_reports, patient_timeline, patients, simple_case
from app.domain.enums import UserRole
from app.domain.simple_case import case_fingerprint, normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest



def test_age_specific_reference_is_selected_without_classification():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 12, "sex": "male"},
            "labs": [
                {
                    "test_name": "ALP",
                    "value": 210,
                    "unit": "U/L",
                    "source_references": [
                        {
                            "text": "Adult: 40-130 U/L",
                            "minimum": 40,
                            "maximum": 130,
                            "unit": "U/L",
                            "age_min": 18,
                        },
                        {
                            "text": "Age 10-17: 80-350 U/L",
                            "minimum": 80,
                            "maximum": 350,
                            "unit": "U/L",
                            "age_min": 10,
                            "age_max": 17,
                        },
                    ],
                }
            ],
            "reports": [
                {
                    "report_type": "ECG",
                    "findings": "Sinus rhythm.",
                }
            ],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text == "Age 10-17: 80-350 U/L"
    assert result.labs[0].reference_source == "report_age_sex_match"
    dumped = result.model_dump()
    assert "classification" not in dumped["labs"][0]
    assert "status" not in dumped["labs"][0]


def test_source_reference_is_preserved_as_is():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 45, "sex": "female"},
            "labs": [
                {
                    "test_name": "TSH",
                    "value": 2.1,
                    "unit": "mIU/L",
                    "source_reference": "0.27 - 4.20",
                }
            ],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text == "0.27 - 4.20"
    assert result.labs[0].reference_source == "report"


def test_missing_reference_creates_warning_but_does_not_invent_one():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 30, "sex": "unknown"},
            "labs": [{"test_name": "Example", "value": 10}],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text is None
    assert result.labs[0].reference_source == "missing"
    assert result.warnings



@pytest.fixture
def context():
    user = SimpleNamespace(id=uuid4(), role=UserRole.PATIENT, is_active=True)
    patient = SimpleNamespace(
        id=uuid4(), protocol_no="TEST-001", sex="unknown",
        metadata_json={"owner_user_id": str(user.id)},
    )
    other = SimpleNamespace(
        id=uuid4(), metadata_json={"owner_user_id": str(uuid4())},
    )
    now = datetime.now(UTC)
    report = SimpleNamespace(
        id=uuid4(), patient_id=patient.id, uploaded_by_user_id=user.id,
        source_type="simple_case_pdf", file_name="lab.pdf", report_date=None,
        status="saved", metadata_json={}, created_at=now, updated_at=now,
    )
    event = SimpleNamespace(id=uuid4(), patient_id=patient.id)
    records = {patient.id: patient, other.id: other}
    session = SimpleNamespace(
        get=AsyncMock(side_effect=lambda model, id: records.get(id)),
        execute=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock(),
        rollback=AsyncMock(),
    )
    repository = SimpleNamespace(get_by_id=AsyncMock(return_value=report))
    timeline_repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=event),
        delete_by_id=AsyncMock(return_value=True),
    )
    timeline_service = SimpleNamespace(
        list_for_patient=AsyncMock(return_value=[]), create_event=AsyncMock(),
    )
    app = FastAPI()
    for module in (lab_reports, patient_timeline, patients, simple_case):
        app.include_router(module.router)

    async def get_session():
        yield session

    app.dependency_overrides[dependencies.get_session] = get_session
    app.dependency_overrides[dependencies.get_lab_report_repository] = lambda: repository
    app.dependency_overrides[dependencies.get_patient_timeline_repository] = lambda: timeline_repository
    app.dependency_overrides[dependencies.get_patient_timeline_service] = lambda: timeline_service
    with TestClient(app) as client:
        yield SimpleNamespace(
            app=app, client=client, user=user, patient=patient, other=other,
            report=report, event=event, session=session, repository=repository,
            timeline_repository=timeline_repository, timeline_service=timeline_service,
        )


def authenticate(context):
    context.app.dependency_overrides[auth.get_current_active_user] = lambda: context.user


def test_anonymous_requests_cannot_read_write_or_call_paid_ai(context, monkeypatch):
    ai = AsyncMock()
    monkeypatch.setattr(simple_case, "interpret_simple_case", ai)
    c = context
    requests = [
        ("GET", f"/lab-reports/{c.report.id}", None),
        ("PATCH", f"/lab-reports/{c.report.id}/patient-metadata", {}),
        ("PATCH", f"/lab-reports/{c.report.id}/clinical-context", {}),
        ("PATCH", f"/lab-reports/{c.report.id}/save", {"patient_id": str(c.patient.id)}),
        ("POST", "/timeline/events", {"patient_id": str(c.patient.id), "event_type": "note", "title": "test"}),
        ("GET", f"/timeline/events/{c.event.id}", None),
        ("GET", f"/timeline/patients/{c.patient.id}", None),
        ("GET", f"/timeline/patients/{c.patient.id}/recent", None),
        ("DELETE", f"/timeline/events/{c.event.id}", None),
        ("POST", "/simple-case/ai-interpretation", {}),
        ("POST", "/simple-case/labs/pdf", None),
        ("POST", "/simple-case/reports/pdf", None),
    ]
    for method, path, body in requests:
        response = c.client.request(method, path, json=body)
        assert response.status_code == 401, (path, response.text)
    ai.assert_not_awaited()
    c.session.commit.assert_not_awaited()
    c.timeline_repository.delete_by_id.assert_not_awaited()


@pytest.mark.parametrize("operation", ["read", "demographics", "clinical", "move"])
def test_patient_cannot_access_or_move_another_patients_report(context, operation):
    c = context
    authenticate(c)
    c.report.patient_id = c.other.id
    old_owner = c.report.uploaded_by_user_id
    base = f"/lab-reports/{c.report.id}"
    requests = {
        "read": ("GET", base, None),
        "demographics": ("PATCH", base + "/patient-metadata", {"age": 45}),
        "clinical": ("PATCH", base + "/clinical-context", {}),
        "move": ("PATCH", base + "/save", {"patient_id": str(c.patient.id)}),
    }
    method, path, body = requests[operation]
    response = c.client.request(method, path, json=body)
    assert response.status_code == 404
    assert c.report.patient_id == c.other.id
    assert c.report.uploaded_by_user_id == old_owner
    c.session.commit.assert_not_awaited()


def test_patient_can_read_and_move_own_report(context):
    c = context
    authenticate(c)
    assert c.client.get(f"/lab-reports/{c.report.id}").status_code == 200
    c.other.metadata_json["owner_user_id"] = str(c.user.id)
    response = c.client.patch(
        f"/lab-reports/{c.report.id}/save", json={"patient_id": str(c.other.id)},
    )
    assert response.status_code == 200
    assert c.report.patient_id == c.other.id
    c.session.commit.assert_awaited_once()


@pytest.mark.parametrize("operation", ["create", "read", "list", "recent", "delete"])
def test_timeline_checks_patient_ownership_before_read_or_mutation(context, operation):
    c = context
    authenticate(c)
    c.event.patient_id = c.other.id
    requests = {
        "create": ("POST", "/timeline/events", {"patient_id": str(c.other.id), "event_type": "note", "title": "test"}),
        "read": ("GET", f"/timeline/events/{c.event.id}", None),
        "list": ("GET", f"/timeline/patients/{c.other.id}", None),
        "recent": ("GET", f"/timeline/patients/{c.other.id}/recent", None),
        "delete": ("DELETE", f"/timeline/events/{c.event.id}", None),
    }
    method, path, body = requests[operation]
    assert c.client.request(method, path, json=body).status_code == 404
    c.timeline_service.create_event.assert_not_awaited()
    c.timeline_service.list_for_patient.assert_not_awaited()
    c.timeline_repository.delete_by_id.assert_not_awaited()
    c.session.commit.assert_not_awaited()


def test_patient_can_list_and_delete_own_timeline(context):
    c = context
    authenticate(c)
    assert c.client.get(f"/timeline/patients/{c.patient.id}").status_code == 200
    assert c.client.delete(f"/timeline/events/{c.event.id}").json() == {"deleted": True}
    c.timeline_repository.delete_by_id.assert_awaited_once_with(c.event.id)


def test_doctor_update_preserves_patient_owner(context, monkeypatch):
    c = context
    authenticate(c)
    c.user.role = UserRole.DOCTOR
    owner = str(uuid4())
    c.patient.metadata_json["owner_user_id"] = owner
    monkeypatch.setattr(patients, "_ensure_protocol_available", AsyncMock())
    # This endpoint uses an ORM response schema; test the transaction directly.
    import asyncio
    from app.schemas.patient_record import PatientRecordUpsert
    payload = PatientRecordUpsert(protocol_no="TEST-001", sex="unknown", age=40)
    asyncio.run(patients.update_patient_record(c.patient.id, payload, c.session, c.user))
    assert c.patient.metadata_json["owner_user_id"] == owner
    assert c.patient.metadata_json["age"] == 40


@pytest.mark.parametrize("matches", [True, False, None])
def test_case_save_keeps_only_ai_report_for_the_same_case(context, monkeypatch, matches):
    c = context
    authenticate(c)
    payload = {"clinical": {"age": 40}, "labs": [{"test_name": "TSH", "value": 2.1}]}
    normalized = normalize_simple_case(SimpleCaseRequest.model_validate(payload)).model_dump(mode="json")
    report = {"report_text": "existing", "model": "mock"}
    if matches is not None:
        report["case_fingerprint"] = case_fingerprint(normalized) if matches else "old-case"
    c.patient.metadata_json["simple_case_ai_report"] = report
    monkeypatch.setattr(simple_case, "_persist_simple_case_sources", AsyncMock())
    response = c.client.put(f"/simple-case/patients/{c.patient.id}/save", json=payload)
    assert response.status_code == 200
    assert ("simple_case_ai_report" in c.patient.metadata_json) is (matches is True)
    saved = c.client.get(f"/simple-case/patients/{c.patient.id}").json()
    assert (saved["ai_report"] is not None) is (matches is True)


def test_saved_case_hides_a_report_for_different_inputs(context):
    c = context
    authenticate(c)
    c.patient.metadata_json.update({
        "simple_case": {"clinical": {"age": 40}},
        "simple_case_ai_report": {"report_text": "stale", "case_fingerprint": "old-case"},
    })
    assert c.client.get(f"/simple-case/patients/{c.patient.id}").json()["ai_report"] is None


def test_authenticated_ai_report_is_bound_to_its_inputs(context, monkeypatch):
    c = context
    authenticate(c)
    monkeypatch.setattr(simple_case, "interpret_simple_case", AsyncMock(return_value=SimpleNamespace(report_text="mock report", model="mock")))
    payload = {"clinical": {"age": 45}, "labs": []}
    response = c.client.post(f"/simple-case/patients/{c.patient.id}/ai-interpretation", json=payload)
    assert response.status_code == 200
    expected = normalize_simple_case(SimpleCaseRequest.model_validate(payload)).model_dump(mode="json")
    assert c.patient.metadata_json["simple_case_ai_report"]["case_fingerprint"] == case_fingerprint(expected)


# LAB DOCUMENT INGESTION v2: documents/models are local or mocked, never live API calls.
from app.domain.canonical_lab_model import SourceContext
from app.domain.lab_document_ingestion import RawLabRow, validate_merge, ingest_lab_document
from app.domain.lab_document_normalizer import DocumentPage, normalize_document, process_image
import asyncio
import io
from PIL import Image
import pymupdf


def raw_row(value='2.1', *, page=1, index=1, **extra):
    return RawLabRow({'raw_parameter_name':'TSH', 'raw_value':value, 'unit':'mIU/L',
                      'reference_text':'0.27 - 4.20', 'reference_min':0.27, 'reference_max':4.2,
                      'confidence':0.95, **extra}, page, index)


def test_ingestion_deduplication_keeps_provenance_and_different_dates_or_statuses():
    rows = [raw_row(), raw_row(page=2), raw_row(measured_at='2026-10-01'),
            raw_row(source_flag='Yüksek')]
    case = validate_merge(rows, SourceContext('photo', file_name='lab.png'))
    assert len(case['labs']) == 3
    assert case['labs'][0]['source_locations'] == [{'page':1, 'row':1}, {'page':2, 'row':1}]
    assert case['labs'][2]['source_flag'] == 'Yüksek'
    assert not case['native_ready']


def test_ingestion_conflicting_values_survive_and_need_review():
    case = validate_merge([raw_row('2.1'), raw_row('9.0')], SourceContext('photo'))
    assert len(case['labs']) == 2
    assert all(r['needs_review'] for r in case['labs'])
    assert all('conflicting_or_repeated_observation' in r['ingestion_reasons'] for r in case['labs'])


def test_ingestion_missing_value_and_name_are_preserved_with_review():
    case = validate_merge([raw_row(None), raw_row('0', raw_parameter_name='', unit=None)], SourceContext('photo'))
    assert len(case['labs']) == 2
    assert 'missing_observed_value' in case['labs'][0]['ingestion_reasons']
    assert 'missing_parameter_name' in case['labs'][1]['ingestion_reasons']
    assert case['labs'][1]['raw_value'] == '0'


def test_ingestion_reversed_references_do_not_replace_printed_source_text():
    case = validate_merge([raw_row(reference_min=10, reference_max=2, reference_text='10 - 2')], SourceContext('photo'))
    assert case['labs'][0]['reference_min'] is None
    assert case['labs'][0]['reference_text'] == '10 - 2'
    assert 'invalid_reference_bounds' in case['labs'][0]['ingestion_reasons']


def image_bytes(size=(600, 800), *, exif=None):
    image = Image.new('RGB', size, 'white')
    output = io.BytesIO()
    image.save(output, format='JPEG', **({'exif':exif} if exif else {}))
    return output.getvalue()


def test_document_processor_honors_exif_and_explicit_rotation():
    exif = Image.Exif(); exif[274] = 6
    page = process_image(image_bytes(exif=exif))
    assert Image.open(io.BytesIO(page.image)).size == (800, 600)
    assert 'exif_orientation' in page.operations
    rotated = process_image(image_bytes(), rotation=90)
    assert Image.open(io.BytesIO(rotated.image)).size == (800, 600)


def test_document_processor_marks_poor_quality_and_rejects_invalid_input():
    page = process_image(image_bytes((300, 300)))
    assert 'low_resolution' in page.warnings
    assert 'low_contrast' in page.warnings
    with pytest.raises(ValueError): normalize_document(b'not a real image', 'image/jpeg')
    with pytest.raises(ValueError): normalize_document(image_bytes(), 'image/jpeg', rotation=45)


def test_pdf_normalization_keeps_every_page_and_rejects_page_limit():
    with pymupdf.open() as doc:
        doc.new_page(); doc.new_page()
        content = doc.tobytes()
    pages = normalize_document(content, 'application/pdf')
    assert [p.number for p in pages] == [1, 2]
    assert all(p.native_pdf for p in pages)
    with pymupdf.open() as doc:
        for _ in range(21): doc.new_page()
        oversized = doc.tobytes()
    with pytest.raises(ValueError, match='1-20'): normalize_document(oversized, 'application/pdf')


def test_multi_page_ingestion_reports_empty_pages_and_row_count_mismatch(monkeypatch):
    import app.domain.lab_document_ingestion as ingestion
    monkeypatch.setattr(ingestion, 'normalize_document', lambda *args, **kwargs:[DocumentPage(1,b'first'),DocumentPage(2,b'second')])
    async def extract(page):
        return {'labs':[raw_row().data], 'visible_row_count':3} if page.number == 1 else {'labs':[], 'visible_row_count':1}
    result = asyncio.run(ingest_lab_document(content=b'pdf', media_type='application/pdf', file_name='lab.pdf', extract_page=extract))
    assert len(result['labs']) == 1
    assert result['page_reports'][0]['row_count_check'] == 'mismatch'
    assert 'page_2:no_lab_rows_on_page_review' in result['warnings']
    assert result['labs'][0]['needs_review']
    assert result['labs'][0]['source_page'] == 1
    assert not result['completeness_verified']


def test_ingestion_unavailable_count_is_explicit_and_not_claimed_complete(monkeypatch):
    import app.domain.lab_document_ingestion as ingestion
    monkeypatch.setattr(ingestion, 'normalize_document', lambda *args, **kwargs:[DocumentPage(1,b'photo')])
    async def extract(page): return {'labs':[raw_row().data]}
    result = asyncio.run(ingest_lab_document(content=b'image', media_type='image/jpeg', file_name='lab.jpg', extract_page=extract))
    assert 'page_1:visible_row_count_unverified' in result['warnings']
    assert result['page_reports'][0]['row_count_check'] == 'unknown'
    assert result['ingestion_contract'] == 'medicore-lab-document-ingestion-v2'


def test_canonical_conversion_has_no_computed_display_classification():
    case = validate_merge([raw_row(source_flag='Normal')], SourceContext('photo', file_name='lab.jpg'))
    rows = simple_case._lab_inputs_from_extracted(case, source_file_name='lab.jpg', extraction_source='v2')
    assert rows[0].value == '2.1'
    assert rows[0].source_metadata['source_flag'] == 'Normal'
    assert 'display_status' not in rows[0].source_metadata
    assert 'display_direction' not in rows[0].source_metadata


def test_clinical_brain_receives_all_results_without_ui_groups():
    from app.domain.simple_case_ai import _build_case_payload
    request = SimpleCaseRequest.model_validate({'labs':[
        {'test_name':'normal','value':2,'source_metadata':{'display_status':'normal'}},
        {'test_name':'high','value':9,'source_metadata':{'source_flag':'Yüksek','needs_review':True}},
        {'test_name':'unknown','value':None},
    ]})
    payload = _build_case_payload(request)
    assert [row['test_name'] for row in payload['labs']] == ['normal','high','unknown']
    assert all('source_classification' not in row for row in payload['labs'])
    assert payload['labs'][1]['source_flag'] == 'Yüksek'
    assert payload['labs'][1]['needs_review'] is True


def test_clinical_brain_rejects_oversized_inputs_without_silent_truncation(monkeypatch):
    import app.domain.simple_case_ai as ai
    monkeypatch.setattr(ai, 'get_settings', lambda:SimpleNamespace(claude_hypothesis_model='same-model', claude_extraction_model=None, claude_vision_model=None, anthropic_api_key='mock-only'))
    monkeypatch.setattr(ai, '_build_case_payload', lambda _: {'labs':'x'*160_001})
    with pytest.raises(RuntimeError, match='sessizce kırpılmadı'):
        asyncio.run(ai.interpret_simple_case(SimpleCaseRequest()))


def test_document_upload_uses_extraction_only_readers(context, monkeypatch):
    c = context; authenticate(c)
    async def fake_ingest(**kwargs):
        page_result = await kwargs['extract_page'](DocumentPage(1, b'normalized'))
        return validate_merge([RawLabRow(page_result['labs'][0],1,1)], SourceContext('photo', file_name='lab.jpg'))
    monkeypatch.setattr(simple_case, 'ingest_lab_document', fake_ingest)
    reader = AsyncMock(return_value={'labs':[raw_row().data]})
    monkeypatch.setattr(simple_case, '_extract_lab_document_with_claude', reader)
    radiology = AsyncMock()
    monkeypatch.setattr(simple_case, 'review_radiology_media', radiology)
    response = c.client.post('/simple-case/labs/image', files={'file':('lab.jpg', b'image', 'image/jpeg')})
    assert response.status_code == 200
    reader.assert_awaited_once()
    radiology.assert_not_awaited()
    assert response.json()[0]['value'] == '2.1'


def test_validation_disagreement_between_raw_and_numeric_values_is_not_hidden():
    case = validate_merge([raw_row('2.1', normalized_value=9)], SourceContext('photo'))
    assert case['labs'][0]['raw_value'] == '2.1'
    assert case['labs'][0]['normalized_value'] is None
    assert 'numeric_value_conflict' in case['labs'][0]['ingestion_reasons']


def test_claude_completeness_retry_failure_keeps_first_reading():
    import json
    from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
    service = object.__new__(ClaudeLabExtractionService)
    service._model = 'unchanged'
    first = SimpleNamespace(content=[SimpleNamespace(type='text', text=json.dumps({
        'values':[{'raw_parameter_name':'TSH','raw_value':'2.1','reference_text':'0.27 - 4.20'}],
        'visible_row_count':3,
    }))])
    service._client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=[first, RuntimeError('audit failed')])))
    class Guard:
        async def call(self, operation): return await operation()
    service._guard = Guard()
    result = asyncio.run(service.extract_from_bytes(b'image', 'lab.png', 'image/png'))
    assert len(result.values) == 1
    assert result.values[0].reference_text == '0.27 - 4.20'
    assert 'image_completeness_audit_failed' in result.warnings
    assert result.overall_needs_review


def test_perspective_processor_only_rectifies_a_clear_document_boundary():
    from PIL import ImageDraw
    image = Image.new('RGB', (800, 1000), 'white')
    draw = ImageDraw.Draw(image)
    draw.polygon([(90,90),(720,140),(740,910),(80,880)], outline='black', width=5)
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    page = process_image(buffer.getvalue())
    assert 'perspective_correction' in page.operations
    assert Image.open(io.BytesIO(page.image)).width < 800


def test_reference_unit_disagreement_is_marked_for_review():
    result = validate_merge([raw_row(reference_unit='mg/dL')], SourceContext('photo'))
    assert 'reference_unit_mismatch' in result['labs'][0]['ingestion_reasons']
    assert result['labs'][0]['reference_unit'] == 'mg/dL'


def test_extraction_deadline_does_not_return_a_seemingly_complete_subset(monkeypatch):
    import app.domain.lab_document_ingestion as ingestion
    monkeypatch.setattr(ingestion, 'normalize_document', lambda *args, **kwargs:[DocumentPage(1,b'image')])
    monkeypatch.setattr(ingestion, 'INGESTION_TIMEOUT_SECONDS', 0.01)
    async def slow(page):
        await asyncio.sleep(0.1)
        return {'labs':[raw_row().data]}
    with pytest.raises(ValueError, match='tamamlanmamış sonuçlar kaydedilmedi'):
        asyncio.run(ingest_lab_document(content=b'image', media_type='image/png', file_name='lab.png', extract_page=slow))
