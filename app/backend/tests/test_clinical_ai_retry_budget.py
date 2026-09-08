from app.domain.openai_lab_clinical_service import _client_for_key


def test_clinical_ai_client_disables_retries() -> None:
    client = _client_for_key("test-key", 8.0)
    assert client.max_retries == 0
