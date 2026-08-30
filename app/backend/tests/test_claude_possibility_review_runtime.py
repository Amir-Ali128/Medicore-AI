from app.domain import claude_clinical_hypothesis_service as service_module
from app.domain.claude_possibility_review_runtime import _ensure_possibility_language


def test_turkish_summary_is_forced_to_possibility_language() -> None:
    summary = (
        "Akut prerenal AKI bulguları, dehidratasyon, hipernatremi; "
        "hekim değerlendirmesi gerekir"
    )

    guarded = _ensure_possibility_language(summary, "tr")

    assert "olabilir" in guarded.lower()
    assert "hekim değerlendirmesi gerekir" in guarded.lower()
    assert len(guarded) <= 120


def test_existing_turkish_possibility_language_is_preserved() -> None:
    summary = "Prerenal patern olabilir; hekim değerlendirmesi gerekir."

    assert _ensure_possibility_language(summary, "tr") == summary


def test_system_prompt_requires_uncertainty_and_physician_review() -> None:
    prompt = service_module._SYSTEM_PROMPT.lower()

    assert "olabilir" in prompt
    assert "physician review is required" in prompt
    assert "never state a diagnosis" in prompt
