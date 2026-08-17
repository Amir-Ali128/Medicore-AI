from app.domain.patient_protocol import (
    generate_protocol_no,
    is_valid_protocol_no,
    normalize_protocol_no,
)


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
