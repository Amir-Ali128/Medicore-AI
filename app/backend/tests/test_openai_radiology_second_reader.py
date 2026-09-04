from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.domain import openai_radiology_second_reader as openai_reader
from app.domain.radiology_provider_comparator import compare_radiology_readers
from app.domain.report_document_image_ai import RadiologyMediaReview


def _review(*, summary: str, observations: list[str]) -> RadiologyMediaReview:
    return RadiologyMediaReview(
        summary=summary,
        observations=observations,
        limitations=[],
        visible_text="",
        model="test-model",
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


def test_openai_second_reader_uses_stateless_responses_image_input(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "document_kind": "MEDICAL_IMAGE",
                        "detected_modality": "XRAY",
                        "detected_body_part": "CHEST",
                        "report_type": "UNKNOWN",
                        "summary": "Sağ apikal bölgede plevral çizgi benzeri görünüm izleniyor; hekim doğrulaması gerekir.",
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

    class FakeClient:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key
            self.responses = FakeResponses()

    monkeypatch.setattr(openai_reader, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        openai_reader,
        "get_settings",
        lambda: SimpleNamespace(
            openai_radiology_second_reader_enabled=True,
            openai_api_key="test-key",
            openai_vision_model="gpt-5.6-terra",
        ),
    )

    result = asyncio.run(
        openai_reader.review_radiology_media_openai(
            content=b"fake-image",
            media_type="image/png",
            modality="XRAY",
            body_part="CHEST",
        )
    )

    assert result is not None
    assert result.model == "gpt-5.6-terra"
    assert result.document_kind == "MEDICAL_IMAGE"
    assert any("pnömotoraks" in item.lower() for item in result.observations)
    assert captured["store"] is False
    assert captured["max_output_tokens"] == 2800

    request = captured["input"]
    assert isinstance(request, list)
    content = request[0]["content"]
    text_item = next(item for item in content if item["type"] == "input_text")
    image_item = next(item for item in content if item["type"] == "input_image")
    assert "BAĞIMSIZ ikinci okuyucusun" in text_item["text"]
    assert image_item["image_url"].startswith("data:image/png;base64,")
    assert image_item["detail"] == "high"


def test_openai_second_reader_is_optional_when_key_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        openai_reader,
        "get_settings",
        lambda: SimpleNamespace(
            openai_radiology_second_reader_enabled=True,
            openai_api_key=None,
            openai_vision_model="gpt-5.6-terra",
        ),
    )

    result = asyncio.run(
        openai_reader.review_radiology_media_openai(
            content=b"fake-image",
            media_type="image/jpeg",
            modality="XRAY",
            body_part="CHEST",
        )
    )
    assert result is None


def test_comparator_surfaces_corroboration_without_calling_it_truth() -> None:
    primary = _review(
        summary="Sağ apikal pnömotoraks şüphesi.",
        observations=["Plevral çizgi seçiliyor."],
    )
    second = _review(
        summary="Right apical pneumothorax could be present.",
        observations=["Apical pleural line is visible."],
    )

    comparison = compare_radiology_readers(primary, second)

    assert "pneumothorax" in comparison["corroborated_concepts"]
    assert comparison["agreement_is_not_validation"] is True
    assert comparison["high_attention_asymmetry"] == []


def test_comparator_flags_high_attention_asymmetry_not_false_disagreement() -> None:
    primary = _review(
        summary="Belirgin akut kemik düzensizliği seçilmiyor.",
        observations=[],
    )
    second = _review(
        summary="Kırık ile uyumlu olabilecek kortikal süreksizlik izleniyor.",
        observations=["Fracture suspicion at the cortex."],
    )

    comparison = compare_radiology_readers(primary, second)

    assert "fracture" in comparison["second_reader_only_concepts"]
    assert "fracture" in comparison["high_attention_asymmetry"]
    assert comparison["requires_physician_attention"] is True
    assert comparison["mode"] == "deterministic_concept_overlap_not_ground_truth"
