from app.domain.openai_lab_extraction_service import _EXTRACTION_TIMEOUT_SECONDS


def test_lab_extraction_timeout_reserves_room_for_clinical_and_db_work() -> None:
    assert _EXTRACTION_TIMEOUT_SECONDS == 18.0
    assert _EXTRACTION_TIMEOUT_SECONDS < 30.0
