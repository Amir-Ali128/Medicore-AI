from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.domain import gemini_radiology_third_reader as gemini_reader
from app.domain.radiology_provider_comparator import compare_radiology_reader_set
from app.domain.report_document_image_ai import RadiologyMediaReview


def _review(*, summary: str, observations: list[str], model: str) -> RadiologyMediaReview:
    return RadiologyMediaReview(
        summary=summary,
        observations=observations,
        limitations=[],
        visible_text="",
        model=model,
        detected_modality="XRAY",
        detected_body_part="CHEST",
        document_kind="MEDICAL_IMAGE",
        report_type="UNKNOWN",
        result_text="",
        result_items=(),
        key_findings=(),
        recommendations=(),
        comparison_text="",
    )


def test_gemini_reader_uses_independent_stateless_multimodal_input(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeInteractions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "document_kind": "MEDICAL_IMAGE",
                        "detected_modality": "XRAY",
                        "detected_body_part": "CHEST",
                        "report_type": "UNKNOWN",
                        "summary": "Sağ apikal plevral çizgi benzeri görünüm izleniyor; hekim doğrulaması gerekir.",
                        "result_text": "",
                        "result_items": [],
                        "key_findings": [],
                        "recommendations": [],
                        "comparison_text": "",
                        "observations": [
                            "Sağ apikal bölgede pnömotoraks ile uyumlu olabilecek plevral çizgi benzeri görünüm seçiliyor."
                        ],
                        "limitations": ["Tek projeksiyon değerlendirmeyi sınırlar."],
                        "visible_text": "",
                    }
                )
            )

    class FakeAio:
        def __init__(self):
            self.interactions = FakeInteractions()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key
            self.aio = FakeAio()

    monkeypatch.setattr(gemini_reader.genai, "Client", FakeClient)
    monkeypatch.setattr(
        gemini_reader,
        "get_settings",
        lambda: SimpleNamespace(
            gemini_radiology_third_reader_enabled=True,
            gemini_api_key="test-gemini-key",
            gemini_vision_model="gemini-3.7-flash",
        ),
    )

    result = asyncio.run(
        gemini_reader.review_radiology_media_gemini(
            content=b"fake-image",
            media_type="image/png",
            modality="XRAY",
            body_part="CHEST",
        )
    )

    assert result is not None
    assert result.model == "gemini-3.7-flash"
    assert result.document_kind == "MEDICAL_IMAGE"
    assert any("pnömotoraks" in item.lower() for item in result.observations)
    assert captured["api_key"] == "test-gemini-key"
    assert captured["store"] is False

    request = captured["input"]
    assert isinstance(request, list)
    text_item = next(item for item in request if item["type"] == "text")
    image_item = next(item for item in request if item["type"] == "image")
    assert "BAĞIMSIZ üçüncü okuyucusun" in text_item["text"]
    assert "Claude veya OpenAI yorumunu görmüyorsun" in text_item["text"]
    assert image_item["mime_type"] == "image/png"
    assert image_item["data"]


def test_gemini_reader_is_optional_when_key_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        gemini_reader,
        "get_settings",
        lambda: SimpleNamespace(
            gemini_radiology_third_reader_enabled=True,
            gemini_api_key=None,
            gemini_vision_model="gemini-3.7-flash",
        ),
    )

    result = asyncio.run(
        gemini_reader.review_radiology_media_gemini(
            content=b"fake-image",
            media_type="image/jpeg",
            modality="XRAY",
            body_part="CHEST",
        )
    )
    assert result is None


def test_three_provider_consensus_counts_mentions_without_probability() -> None:
    readers = {
        "anthropic": _review(
            summary="Sağ apikal pnömotoraks şüphesi.",
            observations=["Plevral çizgi seçiliyor."],
            model="claude-test",
        ),
        "openai": _review(
            summary="Right apical pneumothorax could be present.",
            observations=["Apical pleural line is visible."],
            model="gpt-test",
        ),
        "gemini": _review(
            summary="Belirgin pnömotoraks izlenmiyor.",
            observations=[],
            model="gemini-test",
        ),
    }

    comparison = compare_radiology_reader_set(readers)

    assert comparison["reader_count"] == 3
    assert comparison["providers"] == ["anthropic", "gemini", "openai"]
    assert "pneumothorax" in comparison["corroborated_concepts"]
    assert "pneumothorax" in comparison["polarity_conflicts"]
    votes = comparison["concept_votes"]["pneumothorax"]
    assert votes["positive_or_uncertain"] == ["anthropic", "openai"]
    assert votes["negative"] == ["gemini"]
    assert comparison["requires_physician_attention"] is True
    assert comparison["agreement_is_not_validation"] is True
