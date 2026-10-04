"""Clinical date semantics and conservative reading of labelled source dates."""

from datetime import date, datetime, timezone

import pytest

from app.domain.document_dates import calendar_day, extract_document_dates, resolve_timeline_date
from app.domain.patient_clinical_context import normalize_patient_clinical


def test_sample_date_is_primary_but_release_and_upload_remain_distinct():
    resolved = resolve_timeline_date({
        "specimen_date": "2026-10-02", "measured_at": "2026-10-04",
        "result_date": "2026-10-04", "uploaded_at": "2026-10-04T11:00:00+03:00",
    }, kind="lab")
    assert resolved.date == date(2026, 10, 2)
    assert resolved.source == "specimen_date"
    assert resolved.dates["specimen_date"] == date(2026, 10, 2)
    assert resolved.dates["result_date"] == resolved.dates["uploaded_at"] == date(2026, 10, 4)


@pytest.mark.parametrize("kind", ["ULTRASOUND", "CT", "MRI", "XRAY", "X_RAY", "ECG", "ECHO", "ECHOCARDIOGRAPHY"])
def test_imaging_uses_exam_before_document_or_upload(kind):
    resolved = resolve_timeline_date({
        "exam_date": "2026-10-02", "document_date": "2026-10-04",
        "report_date": "2026-10-04", "uploaded_at": "2026-10-04",
    }, kind=kind)
    assert (resolved.date, resolved.source) == (date(2026, 10, 2), "exam_date")
    assert resolved.dates["document_date"] == date(2026, 10, 4)


@pytest.mark.parametrize("field", ["document_date", "consultation_date"])
def test_consultation_uses_its_own_clinical_document_date(field):
    resolved = resolve_timeline_date({field: "2026-10-03", "uploaded_at": "2026-10-04"}, kind="report")
    assert (resolved.date, resolved.source) == (date(2026, 10, 3), field)


def test_lab_with_only_result_date_does_not_invent_a_specimen_date():
    resolved = resolve_timeline_date({"result_date": "2026-10-04", "uploaded_at": "2026-10-05"}, kind="lab")
    assert resolved.date == date(2026, 10, 4)
    assert resolved.source == "result_date"
    assert resolved.dates["specimen_date"] is None


def test_semantic_dates_in_old_source_metadata_are_read_and_invalid_dates_skipped():
    resolved = resolve_timeline_date({
        "specimen_date": "not-a-date", "measured_at": "2026-10-04",
        "source_metadata": {"specimen_date": "2026-10-02", "result_date": "2026-10-04"},
    }, kind="lab")
    assert resolved.date == date(2026, 10, 2)
    assert resolved.dates["result_date"] == date(2026, 10, 4)


def test_date_only_is_stable_and_upload_timestamp_uses_clinic_timezone():
    assert calendar_day("2026-10-02") == date(2026, 10, 2)
    assert calendar_day(datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)) == date(2026, 10, 3)
    resolved = resolve_timeline_date({"created_at": "2026-10-02T22:30:00Z"}, kind="report")
    assert (resolved.date, resolved.source) == (date(2026, 10, 3), "created_at")
    assert resolved.dates["uploaded_at"] == date(2026, 10, 3)


def test_explicit_label_reader_ignores_birth_and_unlabelled_dates():
    dates = extract_document_dates(
        "Doğum Tarihi: 01.01.1988\n02.10.2026\n"
        "Numune Alma Tarihi: 02.10.2026\nSonuç Tarihi: 04.10.2026\n"
        "Tetkik Tarihi: 2026-10-02\nRapor Tarihi: 04/10/2026\n"
        "Konsültasyon Tarihi: 03.10.2026"
    )
    assert dates == {
        "specimen_date": date(2026, 10, 2), "result_date": date(2026, 10, 4),
        "exam_date": date(2026, 10, 2), "document_date": date(2026, 10, 4),
        "consultation_date": date(2026, 10, 3),
    }
    assert extract_document_dates("Doğum Tarihi: 01.01.1988\n02.10.2026") == {}


def test_conflicting_header_dates_are_not_assigned_to_every_lab_row():
    dates = extract_document_dates(
        "Numune Alma Tarihi: 02.10.2026\nNumune Alma Tarihi: 03.10.2026\n"
        "Sonuç Tarihi: 04.10.2026\nSonuç Tarihi: 04.10.2026"
    )
    assert "specimen_date" not in dates
    assert dates["result_date"] == date(2026, 10, 4)


def test_cleared_canonical_clinical_dates_do_not_revive_legacy_aliases():
    clinical = normalize_patient_clinical({
        "event_date": None, "vitals_event_date": None,
        "examination_date": "2026-10-02", "complaints": ["Halsizlik"],
        "physical_exam": {"measurement_date": "2026-10-03"},
        "vital_signs": {"measurement_date": "2026-10-03", "heart_rate": 108},
    })
    assert clinical.event_date is clinical.vitals_event_date is None
    assert clinical.vital_signs.heart_rate == 108
