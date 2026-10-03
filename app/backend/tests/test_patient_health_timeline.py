from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.domain.enums import ResultStatus, Sex
from app.domain.patient_health_timeline import build_patient_health_timeline


def _patient(**changes: object) -> SimpleNamespace:
    values = {
        "id": uuid4(), "sex": Sex.UNKNOWN, "metadata_json": {},
        "created_at": datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
    }
    return SimpleNamespace(**{**values, **changes})


def _lab(patient_id: UUID, **changes: object) -> SimpleNamespace:
    values = {
        "id": uuid4(), "patient_id": patient_id, "report_date": date(2026, 10, 3),
        "created_at": datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
        "file_name": "blood.pdf", "source_type": "simple_case", "metadata_json": {},
        "raw_payload": {}, "status": "analyzed",
    }
    return SimpleNamespace(**{**values, **changes})


def _result(lab: SimpleNamespace, test: str, value: float, **changes: object) -> SimpleNamespace:
    values = {
        "id": uuid4(), "patient_id": lab.patient_id, "lab_report_id": lab.id,
        "raw_parameter_name": test, "canonical_name": test, "parameter_code": test,
        "raw_value": str(value), "normalized_value": Decimal(str(value)),
        "unit": "mg/L" if test == "CRP" else "g/dL", "measured_at": lab.report_date,
        "created_at": lab.created_at, "updated_at": lab.created_at,
        "metadata_json": {}, "reference_min": None, "reference_max": None,
        "reference_source": None, "result_status": ResultStatus.UNKNOWN,
    }
    return SimpleNamespace(**{**values, **changes})


def _report(patient_id: UUID, **changes: object) -> SimpleNamespace:
    values = {
        "id": uuid4(), "patient_id": patient_id, "report_date": date(2026, 10, 3),
        "created_at": datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
        "file_name": "report.pdf", "source_type": "simple_case", "metadata_json": {},
        "modality": "UNKNOWN", "body_part": "OTHER", "findings_json": [],
        "original_text": "Abdominal ultrasonografik incelemede karaciğer doğal.",
        "impression": None, "summary": "Original report summary", "status": "analyzed",
    }
    return SimpleNamespace(**{**values, **changes})


def _entries(timeline: object, kind: str | None = None) -> list:
    return [entry for group in timeline.groups for entry in group.entries if kind is None or entry.kind == kind]


def _lab_values(timeline: object) -> set[tuple[str, float]]:
    return {(result.test_name, float(result.value)) for entry in _entries(timeline) for result in entry.results}


def test_two_patients_keep_all_laboratory_values_separate() -> None:
    a, b = _patient(), _patient()
    a_lab, b_lab = _lab(a.id), _lab(b.id)
    all_labs = [a_lab, b_lab]
    all_results = [_result(a_lab, "Hb", 8.2), _result(a_lab, "CRP", 120), _result(b_lab, "Hb", 15.1), _result(b_lab, "CRP", 2)]
    a_timeline = build_patient_health_timeline(a, all_labs, all_results, [])
    b_timeline = build_patient_health_timeline(b, all_labs, all_results, [])
    assert _lab_values(a_timeline) == {("Hb", 8.2), ("CRP", 120)}
    assert _lab_values(b_timeline) == {("Hb", 15.1), ("CRP", 2)}
    assert a_timeline.total_lab_results == b_timeline.total_lab_results == 2
    assert all(entry.patient_id == a.id for entry in _entries(a_timeline))
    assert all(entry.patient_id == b.id for entry in _entries(b_timeline))


def test_same_day_report_and_laboratory_are_in_one_date_group() -> None:
    patient = _patient()
    lab, report = _lab(patient.id), _report(patient.id)
    timeline = build_patient_health_timeline(patient, [lab], [_result(lab, "Hb", 13.8)], [report])
    assert len(timeline.groups) == 1
    assert timeline.groups[0].date == date(2026, 10, 3)
    assert {entry.kind for entry in timeline.groups[0].entries} == {"laboratory", "report"}
    assert {entry.source_id for entry in timeline.groups[0].entries} == {lab.id, report.id}
    assert timeline.total_entries == 2


def test_fifty_results_are_reachable_without_truncation() -> None:
    patient = _patient()
    lab = _lab(patient.id)
    rows = [_result(lab, f"Parameter {index}", index + 0.1) for index in range(50)]
    timeline = build_patient_health_timeline(patient, [lab], rows, [])
    actual_rows = [result for entry in _entries(timeline) for result in entry.results]
    assert timeline.total_lab_results == 50
    assert len(actual_rows) == 50
    assert {result.test_name for result in actual_rows} == {row.raw_parameter_name for row in rows}
    assert {result.id for result in actual_rows} == {str(row.id) for row in rows}


def test_august_september_october_results_are_retained_and_ordered() -> None:
    patient = _patient()
    dates = [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 3)]
    labs = [_lab(patient.id, report_date=day) for day in dates]
    rows = [_result(lab, "Hb", value) for lab, value in zip(labs, [12.1, 13.0, 13.8], strict=True)]
    timeline = build_patient_health_timeline(patient, labs, rows, [])
    assert [group.date for group in timeline.groups] == list(reversed(dates))
    assert _lab_values(timeline) == {("Hb", 12.1), ("Hb", 13.0), ("Hb", 13.8)}
    assert timeline.total_lab_results == 3
    assert {entry.source_id for entry in _entries(timeline)} == {lab.id for lab in labs}


def test_real_row_measurement_date_overrides_report_and_upload_date() -> None:
    patient = _patient()
    lab = _lab(patient.id, report_date=date(2026, 10, 2))
    row = _result(lab, "Hb", 12.1, measured_at=date(2026, 8, 1))
    timeline = build_patient_health_timeline(patient, [lab], [row], [])
    assert timeline.groups[0].date == date(2026, 8, 1)
    assert _entries(timeline)[0].date_source == "measured_at"


def test_report_date_is_fallback_when_row_has_no_measurement_date() -> None:
    patient = _patient()
    lab = _lab(patient.id, report_date=date(2026, 9, 1))
    timeline = build_patient_health_timeline(patient, [lab], [_result(lab, "Hb", 13, measured_at=None)], [])
    assert timeline.groups[0].date == date(2026, 9, 1)
    assert _entries(timeline)[0].date_source == "report_date"


def test_date_only_values_are_not_shifted_by_timestamp_timezone() -> None:
    patient = _patient()
    uploaded = datetime(2026, 10, 1, 22, 30, tzinfo=timezone.utc)
    report = _report(patient.id, report_date=date(2026, 10, 1), created_at=uploaded)
    timeline = build_patient_health_timeline(patient, [], [], [report])
    assert timeline.groups[0].date == date(2026, 10, 1)
    assert _entries(timeline)[0].date_source == "report_date"


def test_created_at_fallback_uses_istanbul_calendar_day() -> None:
    patient = _patient()
    uploaded = datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)
    report = _report(patient.id, report_date=None, created_at=uploaded)
    timeline = build_patient_health_timeline(patient, [], [], [report])
    assert timeline.groups[0].date == date(2026, 10, 3)
    assert _entries(timeline)[0].date_source == "created_at"


def test_different_row_dates_split_one_lab_set_without_losing_rows() -> None:
    patient = _patient()
    lab = _lab(patient.id)
    rows = [_result(lab, "Hb", 12.1, measured_at=date(2026, 8, 1)), _result(lab, "CRP", 120, measured_at=date(2026, 10, 3))]
    timeline = build_patient_health_timeline(patient, [lab], rows, [])
    assert [group.date for group in timeline.groups] == [date(2026, 10, 3), date(2026, 8, 1)]
    assert timeline.total_lab_results == 2
    assert _lab_values(timeline) == {("Hb", 12.1), ("CRP", 120)}


def test_clinical_and_structured_vitals_are_distinct_references() -> None:
    clinical = {"complaints": ["Kusma"], "history": ["Hipertansiyon"], "notes": "Ağız kuru", "vital_signs": {"heart_rate": 108, "systolic_bp": 145, "diastolic_bp": 90}}
    patient = _patient(metadata_json={"clinical_context": clinical})
    timeline = build_patient_health_timeline(patient, [], [], [])
    clinical_entries, vital_entries = _entries(timeline, "clinical"), _entries(timeline, "vital_signs")
    assert len(clinical_entries) == len(vital_entries) == 1
    assert clinical_entries[0].clinical.complaints == ["Kusma"]
    assert clinical_entries[0].clinical.notes == "Ağız kuru"
    assert vital_entries[0].vital_signs.heart_rate == 108
    assert clinical_entries[0].source_id == vital_entries[0].source_id == patient.id
    assert clinical_entries[0].source_type == vital_entries[0].source_type == "patient"


def test_historical_lab_context_keeps_earlier_clinical_and_vital_values() -> None:
    patient = _patient(metadata_json={"clinical_context": {"complaints": ["İyileşti"], "vital_signs": {"heart_rate": 72}}})
    lab = _lab(patient.id, report_date=date(2026, 8, 1), metadata_json={"clinical_context": {"complaints": ["Kusma"], "vital_signs": {"heart_rate": 108}}})
    timeline = build_patient_health_timeline(patient, [lab], [_result(lab, "Hb", 12.1)], [])
    historical = next(group for group in timeline.groups if group.date == date(2026, 8, 1))
    assert next(entry for entry in historical.entries if entry.kind == "clinical").clinical.complaints == ["Kusma"]
    assert next(entry for entry in historical.entries if entry.kind == "vital_signs").vital_signs.heart_rate == 108
    assert {entry.vital_signs.heart_rate for entry in _entries(timeline, "vital_signs")} == {72, 108}


def test_foreign_report_lab_context_vitals_and_mismatched_rows_are_excluded() -> None:
    a, b = _patient(), _patient()
    a_lab = _lab(a.id)
    b_lab = _lab(b.id, metadata_json={"clinical_context": {"complaints": ["B secret complaint"], "vital_signs": {"heart_rate": 199}}})
    own = _result(a_lab, "Hb", 8.2)
    wrong_patient = _result(a_lab, "B WRONG PATIENT", 15.1, patient_id=b.id)
    wrong_report = _result(b_lab, "B WRONG REPORT", 2, patient_id=a.id)
    orphan = _result(a_lab, "ORPHAN", 99, lab_report_id=uuid4())
    foreign_report = _report(b.id, original_text="B secret report")
    timeline = build_patient_health_timeline(a, [a_lab, b_lab], [own, wrong_patient, wrong_report, orphan], [foreign_report])
    assert _lab_values(timeline) == {("Hb", 8.2)}
    assert _entries(timeline, "report") == []
    assert _entries(timeline, "clinical") == []
    assert _entries(timeline, "vital_signs") == []
    assert all(entry.patient_id == a.id for entry in _entries(timeline))


def test_urine_results_use_existing_lab_source() -> None:
    patient = _patient()
    lab = _lab(patient.id, metadata_json={"specimen_type": "urine"}, file_name="urine.pdf")
    timeline = build_patient_health_timeline(patient, [lab], [_result(lab, "İdrar lökosit", 4, unit="/HPF")], [])
    assert len(_entries(timeline, "urine_laboratory")) == 1
    entry = _entries(timeline)[0]
    assert entry.source_type == "lab_report"
    assert entry.source_id == lab.id
    assert entry.results[0].test_name == "İdrar lökosit"


def test_report_inference_and_exact_original_text_are_present_in_projection() -> None:
    patient = _patient()
    original = "  Abdominal ultrasonografik incelemede karaciğer doğal.\nSonuç: MRI önerilir.  "
    report = _report(patient.id, original_text=original, modality="MRI")
    timeline = build_patient_health_timeline(patient, [], [], [report])
    entry = _entries(timeline, "report")[0]
    assert entry.inferred_report_type == "ULTRASOUND"
    assert entry.report_type_confidence >= 0.8
    assert entry.report_text == original
    assert entry.source_id == report.id


def test_build_is_read_only_and_empty_patient_has_empty_timeline() -> None:
    patient = _patient()
    lab, report = _lab(patient.id), _report(patient.id)
    row = _result(lab, "Hb", 13.8)
    sources = [patient, lab, report, row]
    snapshots = [deepcopy(vars(source)) for source in sources]
    build_patient_health_timeline(patient, [lab], [row], [report])
    assert [vars(source) for source in sources] == snapshots
    empty = build_patient_health_timeline(_patient(), [], [], [])
    assert empty.groups == []
    assert empty.total_entries == empty.total_lab_results == 0


def test_explicit_foreign_patient_inside_legacy_context_cannot_supply_clinical_or_vitals() -> None:
    a, b = _patient(), _patient()
    stale = {"patient_id": str(b.id), "complaints": ["B secret"], "vital_signs": {"heart_rate": 199}}
    a.metadata_json = {"simple_case": {"clinical": deepcopy(stale)}}
    lab = _lab(a.id, metadata_json={"clinical_context": deepcopy(stale)})
    report = _report(a.id, metadata_json={"clinical_context": deepcopy(stale)})
    timeline = build_patient_health_timeline(a, [lab], [_result(lab, "Hb", 8.2)], [report])
    assert _entries(timeline, "clinical") == _entries(timeline, "vital_signs") == []
    assert _lab_values(timeline) == {("Hb", 8.2)}
    assert len(_entries(timeline, "report")) == 1


def test_legacy_metadata_results_reference_existing_report_and_filter_explicit_foreign_ids() -> None:
    a, b = _patient(), _patient()
    lab = _lab(a.id, metadata_json={"simple_case_results": [
        {"patient_id": str(a.id), "test_name": "Hb", "value": 8.2, "unit": "g/dL"},
        {"patient_id": str(b.id), "test_name": "Hb", "value": 15.1, "unit": "g/dL"},
    ]})
    timeline = build_patient_health_timeline(a, [lab], [], [])
    assert _lab_values(timeline) == {("Hb", 8.2)}
    assert timeline.total_lab_results == 1
    assert _entries(timeline)[0].source_id == lab.id
    assert _entries(timeline)[0].source_path == "metadata_json.simple_case_results"


def test_persisted_lab_rows_take_priority_over_old_metadata_copy() -> None:
    patient = _patient()
    lab = _lab(patient.id, metadata_json={"simple_case_results": [{"test_name": "Hb", "value": 99}]})
    timeline = build_patient_health_timeline(patient, [lab], [_result(lab, "Hb", 8.2)], [])
    assert _lab_values(timeline) == {("Hb", 8.2)}
    assert timeline.total_lab_results == 1


def test_clinical_and_vital_measurement_dates_are_used_separately() -> None:
    clinical = {"examination_date": "2026-09-01", "complaints": ["Kusma"], "vital_signs": {"measurement_date": "2026-09-02", "heart_rate": 108}}
    patient = _patient(metadata_json={"clinical_context": clinical})
    timeline = build_patient_health_timeline(patient, [], [], [])
    assert [group.date for group in timeline.groups] == [date(2026, 9, 2), date(2026, 9, 1)]
    assert timeline.groups[0].entries[0].kind == "vital_signs"
    assert timeline.groups[0].entries[0].date_source == "measurement_date"
    assert timeline.groups[1].entries[0].kind == "clinical"
    assert timeline.groups[1].entries[0].date_source == "examination_date"


def test_undated_legacy_report_is_kept_after_dated_records() -> None:
    patient = _patient()
    dated = _report(patient.id, report_date=date(2026, 10, 1))
    undated = _report(patient.id, report_date=None, created_at=None)
    timeline = build_patient_health_timeline(patient, [], [], [undated, dated])
    assert [group.date for group in timeline.groups] == [date(2026, 10, 1), None]
    assert timeline.groups[-1].entries[0].source_id == undated.id
    assert timeline.groups[-1].entries[0].date_source == "unknown"
