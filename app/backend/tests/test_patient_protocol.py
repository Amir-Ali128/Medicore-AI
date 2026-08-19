import pytest
from pydantic import ValidationError

from app.domain.patient_protocol import (
    generate_protocol_no,
    is_valid_protocol_no,
    normalize_protocol_no,
)
from app.schemas.patient_record import PatientRecordUpsert


def test_generate_protocol_no_uses_medicore_format() -> None:
    protocol_no = generate_protocol_no(year=2026)

    assert protocol_no.startswith("MDC-2026-")
    assert is_valid_protocol_no(protocol_no)


def test_protocol_normalization_is_case_insensitive() -> None:
    protocol_no = generate_protocol_no(year=2026)

    assert normalize_protocol_no(f"  {protocol_no.lower()}  ") == protocol_no
    assert is_valid_protocol_no(f"  {protocol_no.lower()}  ")


def test_protocol_number_is_not_plain_sequential_identifier() -> None:
    first = generate_protocol_no(year=2026)
    second = generate_protocol_no(year=2026)

    assert first != second


def test_patient_can_enter_numeric_or_slash_protocol_number() -> None:
    payload = PatientRecordUpsert(protocol_no=" 2026/001245 ")

    assert payload.protocol_no == "2026/001245"


def test_patient_protocol_is_normalized_to_uppercase() -> None:
    payload = PatientRecordUpsert(protocol_no=" ab-123_c ")

    assert payload.protocol_no == "AB-123_C"


def test_patient_protocol_rejects_spaces_inside_number() -> None:
    with pytest.raises(ValidationError):
        PatientRecordUpsert(protocol_no="ABC 123")
