import json

from app.domain.multisource_summary_runtime import (
    _build_user_prompt_with_source_summaries,
    _vital_flags_with_context,
)


def test_ultrasound_abnormal_flag_opens_context_gate() -> None:
    flags = _vital_flags_with_context(
        {"__medicore_context_flags__": ["ULTRASOUND_ABNORMAL_REVIEW"]}
    )
    assert "ULTRASOUND_ABNORMAL_REVIEW" in flags


def test_source_summaries_are_separate_from_symptoms_in_prompt() -> None:
    raw = _build_user_prompt_with_source_summaries(
        [
            "2 gündür kusma",
            "__MEDICORE_SOURCE_SUMMARY__clinical:Kusma ve sıvı alımı azalmış.",
            "__MEDICORE_SOURCE_SUMMARY__laboratory:Kreatinin yüksek; GFR düşük.",
            "__MEDICORE_SOURCE_SUMMARY__ultrasound:Böbrek USG'de review bulgusu.",
        ],
        ["KREATININ_HIGH"],
        "tr",
    )
    payload = json.loads(raw)

    assert payload["symptoms"] == ["2 gündür kusma"]
    assert payload["summaries"]["laboratory"] == "Kreatinin yüksek; GFR düşük."
    assert payload["summaries"]["ultrasound"] == "Böbrek USG'de review bulgusu."
