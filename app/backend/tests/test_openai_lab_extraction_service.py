from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.domain import openai_lab_extraction_service as lab_reader


def _payload() -> dict[str, object]:
    return {
        "patient_age": 80,
        "patient_sex": "female",
        "report_date": "2026-09-06",
        "labs": [
            {
                "raw_parameter_name": "HbA1c",
                "canonical_name": "HbA1c",
                "raw_value": "9.4",
                "normalized_value": 9.4,
                "unit": "%",
                "reference_min": None,
                "reference_max": 6.5,
                "reference_text": "< 6.5",
                "measured_at": "2026-09-06",
                "needs_review": False,
                "confidence": 0.99,
                "source_file_name": "page-1.jpg",
                "source_page": None,
            }
        ],
        "critical_findings": ["HbA1c kaynak referans üst sınırının üzerinde."],
        "clinical_summary": "Glikoz kontrolü açısından hekim değerlendirmesi gerektiren yükseklikler var.",
        "follow_up_considerations": ["Sonuçları klinik öykü ile birlikte doğrula."],
        "warnings": [],
        "extraction_confidence": 0.98,
    }


def test_batch_images_are_sent_in_one_stateless_structured_request(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps(_payload()))

    class FakeClient:
        def __init__(self, *, api_key, timeout=None, max_retries=None):
            captured["api_key"] = api_key
            captured["client_timeout"] = timeout
            captured["client_max_retries"] = max_retries
            self.responses = FakeResponses()

    monkeypatch.setattr(lab_reader, "AsyncOpenAI", FakeClient)
    lab_reader._client_for_key.cache_clear()
    monkeypatch.setattr(
        lab_reader,
        "get_settings",
        lambda: SimpleNamespace(
            lab_extraction_max_bytes=10 * 1024 * 1024,
            openai_api_key="test-key",
            openai_lab_model="gpt-6-astra",
        ),
    )

    result = asyncio.run(
        lab_reader.extract_lab_documents_with_openai(
            documents=[
                (b"image-one", "image/jpeg", "page-1.jpg"),
                (b"image-two", "image/png", "page-2.png"),
            ]
        )
    )

    assert result["labs"][0]["normalized_value"] == 9.4
    assert captured["model"] == "gpt-6-astra"
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert captured["client_timeout"] == lab_reader._EXTRACTION_TIMEOUT_SECONDS
    assert captured["client_max_retries"] == 0

    request = captured["input"]
    assert isinstance(request, list)
    parts = request[0]["content"]
    images = [part for part in parts if part["type"] == "input_image"]
    assert len(images) == 2
    assert images[0]["image_url"].startswith("data:image/jpeg;base64,")
    assert images[1]["image_url"].startswith("data:image/png;base64,")
    assert all(image["detail"] == "high" for image in images)


def test_pdf_is_sent_directly_as_input_file(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps(_payload()))

    class FakeClient:
        def __init__(self, *, api_key, timeout=None, max_retries=None):
            captured["client_timeout"] = timeout
            captured["client_max_retries"] = max_retries
            self.responses = FakeResponses()

    monkeypatch.setattr(lab_reader, "AsyncOpenAI", FakeClient)
    lab_reader._client_for_key.cache_clear()
    monkeypatch.setattr(
        lab_reader,
        "get_settings",
        lambda: SimpleNamespace(
            lab_extraction_max_bytes=10 * 1024 * 1024,
            openai_api_key="test-key",
            openai_lab_model="gpt-6-astra",
        ),
    )

    asyncio.run(
        lab_reader.extract_lab_document_with_openai(
            content=b"%PDF-test",
            media_type="application/pdf",
            file_name="labs.pdf",
        )
    )

    parts = captured["input"][0]["content"]
    file_part = next(part for part in parts if part["type"] == "input_file")
    assert file_part["filename"] == "labs.pdf"
    assert file_part["file_data"].startswith("data:application/pdf;base64,")
    assert captured["client_timeout"] == lab_reader._EXTRACTION_TIMEOUT_SECONDS
    assert captured["client_max_retries"] == 0


def test_missing_api_key_fails_before_provider_call(monkeypatch) -> None:
    monkeypatch.setattr(
        lab_reader,
        "get_settings",
        lambda: SimpleNamespace(
            lab_extraction_max_bytes=10 * 1024 * 1024,
            openai_api_key=None,
            openai_lab_model="gpt-6-astra",
        ),
    )

    with pytest.raises(lab_reader.OpenAILabExtractionError, match="OPENAI_API_KEY"):
        asyncio.run(
            lab_reader.extract_lab_document_with_openai(
                content=b"image",
                media_type="image/jpeg",
                file_name="lab.jpg",
            )
        )
