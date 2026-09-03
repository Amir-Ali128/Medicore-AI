from app.domain.radiology_multi_model_ai import (
    CandidateCondition,
    ProviderImageOpinion,
    _group_conditions,
    _openai_output_text,
    _provider_prompt,
)


def _opinion(provider: str, condition: str) -> ProviderImageOpinion:
    return ProviderImageOpinion(
        provider=provider,
        model="test-model",
        document_kind="MEDICAL_IMAGE",
        detected_modality="XRAY",
        detected_body_part="CHEST",
        summary="Test",
        observations=("Sağ apikal plevral çizgi seçiliyor.",),
        candidate_conditions=(
            CandidateCondition(
                label=condition,
                support="Sağ apikal plevral çizgi",
                confidence="moderate",
            ),
        ),
        critical_flags=(),
        limitations=(),
    )


def test_three_provider_agreement_becomes_strong_consensus() -> None:
    consensus, solo = _group_conditions(
        [
            _opinion("anthropic", "Pnömotoraks"),
            _opinion("openai", "Pnömotoraks olasılığı"),
            _opinion("gemini", "Pnömotoraks"),
        ]
    )

    assert len(consensus) == 1
    assert consensus[0]["supporting_provider_count"] == 3
    assert consensus[0]["agreement_strength"] == "strong"
    assert solo == []


def test_single_provider_candidate_is_not_promoted_to_consensus() -> None:
    consensus, solo = _group_conditions(
        [
            _opinion("openai", "Plevral efüzyon"),
            ProviderImageOpinion(
                provider="gemini",
                model="test-model",
                document_kind="MEDICAL_IMAGE",
                detected_modality="XRAY",
                detected_body_part="CHEST",
                summary="Test",
                observations=(),
                candidate_conditions=(),
                critical_flags=(),
                limitations=(),
            ),
        ]
    )

    assert consensus == []
    assert len(solo) == 1
    assert solo[0]["agreement_strength"] == "single_model"


def test_openai_response_text_parser_supports_responses_api_shape() -> None:
    text = _openai_output_text(
        {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": '{"document_kind":"MEDICAL_IMAGE"}'}
                    ]
                }
            ]
        }
    )
    assert "MEDICAL_IMAGE" in text


def test_provider_prompt_requires_candidate_not_final_diagnosis() -> None:
    prompt = _provider_prompt("XRAY", "ABDOMEN")
    assert "kesin tanı değildir" in prompt
    assert "candidate_conditions" in prompt
    assert "Yüzde olasılık verme" in prompt
    assert "Tek ekran görüntüsünden CT/MR serisinin tamamı" in prompt
