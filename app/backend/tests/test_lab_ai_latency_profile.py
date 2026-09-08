from app.core.config import Settings
from app.domain.openai_lab_clinical_service import _CLINICAL_MAX_OUTPUT_TOKENS


def test_lab_clinical_model_is_decoupled_from_extraction_model() -> None:
    settings = Settings(_env_file=None)

    assert settings.openai_lab_model == "gpt-6-astra"
    assert settings.openai_lab_clinical_model == "gpt-5.6-luna"
    assert settings.openai_lab_clinical_model != settings.openai_lab_model


def test_lab_clinical_output_budget_is_bounded_for_latency() -> None:
    assert _CLINICAL_MAX_OUTPUT_TOKENS == 3200
