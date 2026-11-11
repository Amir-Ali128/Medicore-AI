
from tests.test_privacy_gateway import synthetic_image
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



def test_age_specific_reference_is_selected_before_deterministic_classification():
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
    assert dumped["labs"][0]["status"] == "NORMAL"
    assert dumped["labs"][0]["reference_low"] == 80
    assert dumped["labs"][0]["reference_high"] == 350


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


def test_patient_can_read_but_cannot_move_an_archived_report(context):
    c = context
    authenticate(c)
    assert c.client.get(f"/lab-reports/{c.report.id}").status_code == 200
    c.other.metadata_json["owner_user_id"] = str(c.user.id)
    response = c.client.patch(
        f"/lab-reports/{c.report.id}/save", json={"patient_id": str(c.other.id)},
    )
    assert response.status_code == 409
    assert c.report.patient_id == c.patient.id
    c.session.commit.assert_not_awaited()


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
    monkeypatch.setattr(patients, "ensure_case_name_available", AsyncMock())
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


@pytest.mark.parametrize('confidence', [0.6, float('nan'), 2, True])
def test_duplicate_keeps_lower_or_invalid_extraction_confidence(confidence):
    case = validate_merge([raw_row(), raw_row(page=2, confidence=confidence)], SourceContext('photo'))
    assert len(case['labs']) == 1
    assert case['labs'][0]['confidence'] <= 0.6
    assert case['labs'][0]['needs_review']
    assert 'low_input_confidence' in case['labs'][0]['ingestion_reasons']


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


@pytest.mark.usefixtures("synthetic_privacy_ocr")
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
    result = asyncio.run(service.extract_from_bytes(synthetic_image(), 'lab.png', 'image/png'))
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


@pytest.mark.parametrize('result', [None, {'labs': [], 'visible_row_count': 0}])
def test_empty_document_is_rejected_before_canonical_conversion(monkeypatch, result):
    import app.domain.lab_document_ingestion as ingestion
    from app.domain.lab_document_errors import LabDocumentReadError
    monkeypatch.setattr(ingestion, 'normalize_document', lambda *args, **kwargs: [DocumentPage(1, b'image')])
    async def extract(page): return result
    with pytest.raises(LabDocumentReadError, match='Belgeden laboratuvar sonucu okunamadı') as caught:
        asyncio.run(ingest_lab_document(content=b'image', media_type='image/png', file_name='lab.png', extract_page=extract))
    assert caught.value.page_reports[0]['extracted_rows'] == 0
    assert 'Canonical' not in str(caught.value)


@pytest.mark.parametrize(('status', 'code'), [(401, 'access_denied'), (403, 'access_denied'),
                                          (404, 'model_unavailable'), (429, 'rate_or_quota_limit')])
def test_reader_diagnostics_unwrap_provider_errors_without_exposing_data(status, code):
    from app.domain.lab_document_errors import reader_failure
    provider = RuntimeError('sensitive-provider-body sk-secret patient-name')
    provider.status_code = status
    wrapper = RuntimeError('dependency call failed')
    wrapper.__cause__ = provider
    failure = reader_failure('Claude', wrapper)
    assert failure['code'] == code
    assert failure['status'] == status
    assert 'sk-secret' not in str(failure)
    assert 'patient-name' not in str(failure)


@pytest.mark.parametrize(('media_type', 'filename', 'endpoint'), [
    ('image/jpeg', 'lab.jpg', 'image'), ('application/pdf', 'lab.pdf', 'pdf'),
])
def test_upload_explains_reader_failures_instead_of_empty_canonical_error(context, monkeypatch, caplog, media_type, filename, endpoint):
    import app.domain.lab_document_ingestion as ingestion
    c = context; authenticate(c)
    monkeypatch.setattr(ingestion, 'normalize_document', lambda *args, **kwargs: [DocumentPage(1, b'normalized')])
    monkeypatch.setattr(simple_case, 'get_settings', lambda: SimpleNamespace(
        anthropic_api_key='mock-only', claude_extraction_model='existing-model', claude_vision_model='existing-model',
    ))
    provider = RuntimeError('sensitive-body sk-secret')
    provider.status_code = 401
    service = SimpleNamespace(extract_from_bytes=AsyncMock(side_effect=provider))
    monkeypatch.setattr(simple_case, 'ClaudeLabExtractionService', lambda **kwargs: service)
    monkeypatch.setattr(simple_case, 'extract_lab_document_with_openai', AsyncMock(side_effect=
        simple_case.OpenAILabExtractionError('OPENAI_API_KEY yapılandırılmamış.')))
    response = c.client.post(f'/simple-case/labs/{endpoint}', files={'file': (filename, b'document', media_type)})
    assert response.status_code == 422
    detail = response.json()['detail']
    assert 'Claude: belge okuma erişimi reddedildi' in detail
    assert 'OpenAI: belge okuma yapılandırması eksik' in detail
    assert 'Canonical' not in detail
    assert 'sk-secret' not in detail + caplog.text
    assert 'code=access_denied' in caplog.text
    assert 'code=not_configured' in caplog.text


def test_successful_fallback_still_imports_all_rows_after_claude_failure(context, monkeypatch):
    import app.domain.lab_document_ingestion as ingestion
    c = context; authenticate(c)
    monkeypatch.setattr(ingestion, 'normalize_document', lambda *args, **kwargs: [DocumentPage(1, b'normalized')])
    monkeypatch.setattr(simple_case, '_extract_lab_document_with_claude', AsyncMock(return_value={
        'labs': [], 'extraction_errors': [{'reader': 'Claude', 'code': 'request_failed', 'message': 'failed'}],
    }))
    reader = AsyncMock(return_value={'labs': [raw_row('2.1').data, raw_row('0', raw_parameter_name='CRP').data]})
    monkeypatch.setattr(simple_case, 'extract_lab_document_with_openai', reader)
    response = c.client.post('/simple-case/labs/image', files={'file': ('lab.jpg', b'document', 'image/jpeg')})
    assert response.status_code == 200
    assert [row['value'] for row in response.json()] == ['2.1', '0']
    reader.assert_awaited_once()


def test_claude_invalid_optional_cell_does_not_discard_other_rows_or_source_strings():
    import json
    from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
    service = object.__new__(ClaudeLabExtractionService)
    result = service._parse_result(json.dumps({'values': [
        {'raw_parameter_name': 'TSH', 'raw_value': '2,1', 'normalized_value': 'not-a-number',
         'measured_at': 'unreadable', 'reference_text': '0,27 - 4,20'},
        {'raw_parameter_name': 'CRP', 'raw_value': '0', 'normalized_value': 0},
    ], 'visible_row_count': 2}), 'lab.jpg')
    assert len(result.values) == 2
    assert result.values[0].raw_value == '2,1'
    assert result.values[0].reference_text == '0,27 - 4,20'
    assert result.values[0].normalized_value is None
    assert result.values[0].measured_at is None
    assert result.values[0].needs_review
    assert result.values[1].normalized_value == 0
    assert result.overall_needs_review
    assert 'extraction_invalid_cells_review' in result.warnings


def test_claude_invalid_metadata_keeps_readable_rows_and_requires_review():
    import json
    from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
    service = object.__new__(ClaudeLabExtractionService)
    result = service._parse_result(json.dumps({'values': [{'raw_parameter_name': 'TSH', 'raw_value': '2.1'}],
                                              'visible_row_count': 'unknown', 'warnings': {}}), 'lab.jpg')
    assert len(result.values) == 1
    assert result.visible_row_count is None
    assert result.overall_needs_review


@pytest.mark.usefixtures("synthetic_privacy_ocr")
def test_lab_reading_uses_its_own_budget_when_generic_ai_timeout_is_short(monkeypatch):
    import json
    import anthropic
    import app.domain.claude_lab_extraction_service as reader
    import app.infrastructure.runtime_resilience as resilience
    settings = SimpleNamespace(ai_call_timeout_seconds=0.01, lab_document_read_timeout_seconds=0.2,
                               ai_queue_timeout_seconds=0.01, ai_max_concurrency=1,
                               ai_circuit_breaker_failures=3, ai_circuit_breaker_recovery_seconds=30)
    monkeypatch.setattr(reader, 'get_settings', lambda: settings)
    monkeypatch.setattr(resilience, 'get_settings', lambda: settings)
    captured = {}
    async def slow_response(**kwargs):
        captured['model'] = kwargs['model']
        await asyncio.sleep(0.03)
        return SimpleNamespace(content=[SimpleNamespace(type='text', text=json.dumps({
            'values': [{'raw_parameter_name': 'TSH', 'raw_value': '2.1'}], 'visible_row_count': 1,
        }))])
    create = AsyncMock(side_effect=slow_response)
    def client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(anthropic, 'AsyncAnthropic', client)
    resilience.reset_dependency_guards_for_tests()
    try:
        service = reader.ClaudeLabExtractionService(api_key='mock-only', model='existing-model')
        async def scenario():
            result = await service.extract_from_bytes(synthetic_image(), 'lab.png', 'image/png')
            other = resilience.get_anthropic_guard('other-purpose')
            with pytest.raises(resilience.DependencyTimeoutError):
                await other.call(lambda: asyncio.sleep(0.03))
            return result
        result = asyncio.run(scenario())
        assert len(result.values) == 1
        assert captured['timeout'] == 0.2
        assert captured['max_retries'] == 0
        assert captured['model'] == 'existing-model'
        assert create.await_count == 1
    finally:
        resilience.reset_dependency_guards_for_tests()



@pytest.mark.usefixtures("synthetic_privacy_ocr")
def test_known_small_table_count_skips_unnecessary_second_provider_call():
    import json
    from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
    service = object.__new__(ClaudeLabExtractionService)
    service._model = 'existing-model'
    response = SimpleNamespace(content=[SimpleNamespace(type='text', text=json.dumps({
        'values': [{'raw_parameter_name': 'TSH', 'raw_value': '2.1'}], 'visible_row_count': 1,
    }))])
    create = AsyncMock(return_value=response)
    service._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    class Guard:
        async def call(self, operation): return await operation()
    service._guard = Guard()
    result = asyncio.run(service.extract_from_bytes(synthetic_image(), 'lab.png', 'image/png'))
    assert len(result.values) == 1
    create.assert_awaited_once()
    assert 'image_full_table_audit_retry' not in result.warnings



@pytest.mark.usefixtures("synthetic_privacy_ocr")
def test_missing_row_count_still_triggers_completeness_audit():
    import json
    from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
    service = object.__new__(ClaudeLabExtractionService)
    service._model = 'existing-model'
    def response(rows, count):
        return SimpleNamespace(content=[SimpleNamespace(type='text', text=json.dumps({
            'values': rows, 'visible_row_count': count,
        }))])
    first = [{'raw_parameter_name': 'TSH', 'raw_value': '2.1'}]
    second = [*first, {'raw_parameter_name': 'CRP', 'raw_value': '0'}]
    create = AsyncMock(side_effect=[response(first, 2), response(second, 2)])
    service._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    class Guard:
        async def call(self, operation): return await operation()
    service._guard = Guard()
    result = asyncio.run(service.extract_from_bytes(synthetic_image(), 'lab.png', 'image/png'))
    assert [row.raw_parameter_name for row in result.values] == ['TSH', 'CRP']
    assert create.await_count == 2
    assert 'image_full_table_audit_retry' in result.warnings



@pytest.mark.usefixtures("synthetic_privacy_ocr")
def test_slow_audit_is_cancelled_without_discarding_first_rows(monkeypatch):
    import json
    import app.domain.claude_lab_extraction_service as reader
    from app.infrastructure.runtime_resilience import AsyncDependencyGuard
    # The timeout now includes local privacy redaction before the SDK call.
    monkeypatch.setattr(reader, '_AUDIT_TIMEOUT_SECONDS', 0.2)
    service = object.__new__(reader.ClaudeLabExtractionService)
    service._model = 'existing-model'
    cancelled = []
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return SimpleNamespace(content=[SimpleNamespace(type='text', text=json.dumps({
                'values': [{'raw_parameter_name': 'TSH', 'raw_value': '2.1'}], 'visible_row_count': 2,
            }))])
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.append(True)
    service._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    service._guard = AsyncDependencyGuard('audit-test', timeout_seconds=0.5, queue_timeout_seconds=0.01,
                                          max_concurrency=1, failure_threshold=3, recovery_seconds=30)
    result = asyncio.run(service.extract_from_bytes(synthetic_image(), 'lab.png', 'image/png'))
    assert len(result.values) == 1
    assert result.values[0].raw_value == '2.1'
    assert result.overall_needs_review
    assert 'image_completeness_audit_failed' in result.warnings
    assert cancelled == [True]
    assert service._guard.snapshot()['in_flight'] == 0



@pytest.mark.parametrize('timeout', [0, 29, 81, 180])
def test_document_read_budget_rejects_values_outside_document_deadline(timeout):
    from app.core.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, lab_document_read_timeout_seconds=timeout)


def test_ingestion_numeric_agreement_with_units_and_scientific_notation_preserves_conflicts():
    from app.domain.lab_document_ingestion import RawLabRow, validate_merge
    from app.domain.canonical_lab_model import SourceContext
    for raw,unit,numeric,conflict in [('94 mg/L','mg/L',94,False),('1.48e1','10^9/L',14.8,False),
                                     ('94 mg/L','mg/L',9,True),('2+','mg/L',2,True)]:
        case=validate_merge([RawLabRow({'raw_parameter_name':'Test','raw_value':raw,'unit':unit,'normalized_value':numeric},1,1)],SourceContext('file_upload'))
        row=case['labs'][0]
        assert row['raw_value']==raw
        assert ('numeric_value_conflict' in row['ingestion_reasons']) is conflict
        assert row['reader_normalized_value']==str(numeric)
        if conflict:assert row['normalized_value'] is None and row['needs_review']
    case=validate_merge([RawLabRow({'raw_parameter_name':'Test','raw_value':'≥90','normalized_value':90},1,1)],SourceContext('file_upload'))
    assert case['labs'][0]['normalized_value'] is None


def test_different_source_document_dates_do_not_create_spurious_observation_conflicts():
    from app.domain.lab_document_ingestion import RawLabRow,validate_merge
    from app.domain.canonical_lab_model import SourceContext
    rows=[RawLabRow({'raw_parameter_name':'Creatinine','raw_value':value,'unit':'mg/dL',
                    'reference_text':'0.5–1.0','document_date':day},1,index)
          for index,(value,day) in enumerate([('0.91','2026-02-01'),('1.98','2026-02-03')],1)]
    case=validate_merge(rows,SourceContext('file_upload'))
    assert len(case['labs'])==2
    assert all('conflicting_or_repeated_observation' not in row['ingestion_reasons'] for row in case['labs'])
    rows[1].data['document_date']='2026-02-01'
    conflict=validate_merge(rows,SourceContext('file_upload'))
    assert all('conflicting_or_repeated_observation' in row['ingestion_reasons'] for row in conflict['labs'])


def test_local_pdf_numeric_and_reference_parsers_share_verified_grammar():
    from app.domain.fast_pdf_lab_parser import _parse_numeric_value,_parse_reference
    assert _parse_numeric_value('≥90')==(90,'>=')
    assert _parse_numeric_value('0.42 ng/mL','ng/mL')==(.42,None)
    assert _parse_numeric_value('3+')==(None,None)
    assert _parse_reference('Reference: <5')==(None,5,'Reference: <5')
    assert _parse_reference('Ref: 4,0–10,0')==(4,10,'Ref: 4,0–10,0')


def test_verified_inline_unit_does_not_create_false_missing_unit_review():
    from app.domain.lab_document_ingestion import RawLabRow,validate_merge
    from app.domain.canonical_lab_model import SourceContext
    output=validate_merge([RawLabRow({'raw_parameter_name':'CRP','raw_value':'94 mg/L','reference_text':'<5 mg/L'},1,1)],SourceContext('file_upload'))
    row=output['labs'][0]
    assert row['unit'] is None and row['raw_value']=='94 mg/L'
    assert 'missing_unit' not in row['ingestion_reasons'] and row['normalized_value']==94


def reference_table_pdf(headers, rows, *, add_unsupported=False, document_stamp=None):
    """Synthetic ruled source geometry; no uploaded document is committed."""
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((35,35),'Synthetic source report for deterministic laboratory extraction. '*3,fontsize=7)
        def draw_table(top,columns,body):
            xs=[35+i*min(160,(page.rect.width-70)/len(columns)) for i in range(len(columns)+1)]
            for index,line in enumerate([columns,*body]):
                for col,text in enumerate(line):
                    page.insert_text((xs[col]+6,top+index*28+18),str(text),fontsize=10)
            for x in xs:page.draw_line((x,top),(x,top+(len(body)+1)*28))
            for index in range(len(body)+2):page.draw_line((xs[0],top+index*28),(xs[-1],top+index*28))
        draw_table(100,headers,rows)
        if add_unsupported:draw_table(430,['Test','03.02','04.02'],[['Creatinine','0.91','1.72 mg/dL']])
        if document_stamp:draw_table(530,['Belge','01/02'],[['Tarih / Saat',document_stamp],['Belge turu','Laboratory']])
        return doc.tobytes()


def test_three_column_pdf_table_keeps_every_source_reference_without_provider_inference():
    from app.domain.fast_pdf_lab_parser import try_fast_pdf_lab_case
    rows=[['WBC','14.8 x10^9/L','4.0-10.0'],['Neutrophils','%82','40-75'],
          ['CRP','94 mg/L','<5'],['Procalcitonin','0.42 ng/mL','<0.10'],
          ['Creatinine','0.91 mg/dL','0.5-1.0'],['AST','31 U/L','<35']]
    content=reference_table_pdf(['Test','Sonuc','Referans'],rows)
    case=try_fast_pdf_lab_case(content=content,media_type='application/pdf',file_name='synthetic.pdf',source_type='file_upload')
    assert case and case['visible_row_count']==6
    assert 'source_reference_table_parser_v1' in case['warnings']
    result=simple_case._lab_inputs_from_extracted(case,source_file_name='synthetic.pdf',extraction_source='local')
    assert [r.value for r in result]==[r[1] for r in rows]
    assert [r.source_reference for r in result]==[r[2] for r in rows]
    assert [r.status for r in result]==['HIGH','HIGH','HIGH','HIGH','NORMAL','NORMAL']
    assert all(r.source_metadata['source_page']==1 for r in result)


def test_reference_table_missing_cells_or_unsupported_date_table_defers_without_partial_read():
    from app.domain.fast_pdf_lab_parser import _extract_source_reference_rows
    valid=[['CRP','94 mg/L','<5']]
    assert _extract_source_reference_rows(reference_table_pdf(['Test','Sonuc','Referans'],valid,add_unsupported=True))==[]
    assert _extract_source_reference_rows(reference_table_pdf(['Test','Sonuc','Referans'],[['CRP','','<5']]))==[]
    assert _extract_source_reference_rows(reference_table_pdf(['Test','Sonuc'],[['CRP','94 mg/L']]))==[]


def test_four_column_table_preserves_conflicting_units_and_missing_references_for_review():
    from app.domain.fast_pdf_lab_parser import _extract_source_reference_rows
    source=reference_table_pdf(['Test','Sonuc','Birim','Referans'],[
        ['CRP','94 mg/dL','mg/L','<5'],['Creatinine','1.98','mg/dL','']])
    rows=_extract_source_reference_rows(source)
    assert len(rows)==2 and rows[0]['raw_value']=='94 mg/dL' and rows[0]['unit']=='mg/L'
    case=validate_merge([RawLabRow(row,1,index) for index,row in enumerate(rows,1)],SourceContext('file_upload'))
    output=simple_case._lab_inputs_from_extracted(case,source_file_name='synthetic.pdf',extraction_source='local')
    assert all(r.status=='UNKNOWN' for r in output)
    assert output[1].source_reference is None and output[1].source_metadata['needs_review']


def test_three_column_upload_never_calls_cloud_and_is_independent_of_diagnostic_title(monkeypatch):
    import asyncio
    from fastapi import UploadFile
    from io import BytesIO
    content=reference_table_pdf(['Test','Sonuc','Referans'],[['CRP','94 mg/L','<5']])
    cloud=AsyncMock(side_effect=AssertionError('Source reference is available locally'))
    monkeypatch.setattr(simple_case,'_extract_lab_document_with_claude',cloud)
    output=asyncio.run(simple_case._ingest_lab_upload(UploadFile(BytesIO(content),filename='Normal_vs_High_diagnostic_title.pdf'),'application/pdf'))
    assert len(output)==1 and output[0].status=='HIGH' and output[0].source_reference=='<5'
    cloud.assert_not_awaited()


def test_explicit_document_metadata_date_never_becomes_specimen_or_result_date():
    from app.domain.fast_pdf_lab_parser import _extract_source_reference_rows
    content=reference_table_pdf(['Test','Sonuc','Referans'],[['CRP','94 mg/L','<5']],document_stamp='03.02.2026 08:48')
    rows=_extract_source_reference_rows(content)
    assert len(rows)==1 and rows[0]['document_date']=='2026-02-03'
    assert rows[0].get('specimen_date') is None and rows[0].get('result_date') is None
    assert rows[0]['measured_at'] is None
