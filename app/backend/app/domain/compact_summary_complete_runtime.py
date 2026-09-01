"""Allow complete multi-sentence compact clinical summaries.

The previous compact path capped the model and stored summary at 120 characters,
which could visibly cut Turkish text mid-sentence. This final runtime layer raises
that bound while keeping the response compact and explicitly non-diagnostic.
"""

from __future__ import annotations

from typing import Any

from app.domain import claude_clinical_hypothesis_service as service_module
from app.domain import claude_possibility_review_runtime as possibility_module
from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


service_module._MAX_OUTPUT_TOKENS = 320
service_module._MAX_SUMMARY_CHARS = 700
possibility_module._MAX_SUMMARY_CHARS = 700

service_module._SYSTEM_PROMPT = (
    "You assist a licensed physician. Input contains short clinical, abnormal laboratory, "
    "and when available ultrasound result summaries plus backend-generated review flags. "
    "Write a coherent 2-4 sentence clinical synthesis. Mention only patterns supported by "
    "the supplied data. Never state a diagnosis as established fact; use uncertainty wording "
    "such as 'olabilir', 'ile ilişkili olabilir', 'may' or 'could'. Do not recommend treatment, "
    "medication, or automatic orders. State that physician review is required. Keep the summary "
    "under 500 characters and always finish complete sentences. Return ONLY JSON: "
    '{"risk":1|2|3,"summary":"complete 2-4 sentence synthesis"}.'
)

_original_parse = ClaudeClinicalHypothesisService._parse_compact_output


def _finish_sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return cleaned
    # The model is asked to stay below 500 characters, while storage allows 700.
    # This leaves enough headroom that normal responses are never sliced. As a final
    # guard, do not leave a visibly unfinished last token on screen.
    if cleaned[-1] not in ".!?":
        cleaned = f"{cleaned.rstrip(' ,;:')}."
    return cleaned[:700]


@classmethod
def _parse_complete_summary(
    cls: type[ClaudeClinicalHypothesisService],
    payload: dict[str, Any] | None,
    *,
    flags: list[str],
    language: str,
) -> tuple[int, str]:
    del cls
    risk, summary = _original_parse(payload, flags=flags, language=language)
    return risk, _finish_sentence(summary)


ClaudeClinicalHypothesisService._parse_compact_output = _parse_complete_summary
