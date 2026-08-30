import json

from app.domain.claude_clinical_hypothesis_service import (
    ClaudeClinicalHypothesisService,
)
from app.schemas.clinical_copilot import ClinicalHypothesisGenerationRequest


def test_default_hypothesis_count_is_compact() -> None:
    request = ClinicalHypothesisGenerationRequest()

    assert request.max_hypotheses == 3
    assert ClaudeClinicalHypothesisService._output_token_budget(3) == 1216


def test_output_budget_has_hard_cap() -> None:
    assert ClaudeClinicalHypothesisService._output_token_budget(10) == 2048


def test_context_sanitizer_reduces_large_free_text() -> None:
    context = {
        "history": "x" * 20_000,
        "complaint": "y" * 20_000,
    }

    cleaned = ClaudeClinicalHypothesisService._sanitize_context(context)
    serialized = json.dumps(cleaned)

    # Two 20k fields must be reduced to a small bounded prompt payload.
    assert len(serialized) < 7_000
