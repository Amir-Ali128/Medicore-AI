from app.domain import multisource_summary_runtime as _multisource_summary_runtime  # noqa: F401
from app.domain.source_only_case_evaluation import (
    _risk_display_for_coverage,
    _source_only_fallback,
    source_coverage,
)


def test_clinical_only_is_single_source() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": False,
                "radiology": False,
            },
            "source_summaries": {
                "clinical": "Baş ağrısı",
                "laboratory": "",
                "radiology": "",
            },
        }
    )

    assert coverage["available_count"] == 1
    assert coverage["mode"] == "single_source"
    assert coverage["limited"] is True
    assert coverage["available"] == {
        "clinical": True,
        "laboratory": False,
        "radiology": False,
    }


def test_clinical_and_radiology_is_partial_multisource() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": False,
                "radiology": True,
            }
        }
    )

    assert coverage["available_count"] == 2
    assert coverage["mode"] == "partial_multisource"
    assert coverage["limited"] is True


def test_legacy_ultrasound_summary_maps_to_radiology_source() -> None:
    coverage = source_coverage(
        {
            "source_summaries": {
                "clinical": "",
                "laboratory": "",
                "ultrasound": "Böbrekte taş izlenmiştir.",
            }
        }
    )

    assert coverage["available_count"] == 1
    assert coverage["available"]["radiology"] is True


def test_explicit_false_cannot_be_overridden_by_placeholder_summary() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": False,
                "radiology": False,
            },
            "source_summaries": {
                "clinical": "Baş ağrısı",
                "laboratory": "Laboratuvar verisi bulunamadı.",
                "radiology": "Radyoloji sonucu bulunamadı.",
            },
        }
    )

    assert coverage["available_count"] == 1
    assert coverage["available"]["laboratory"] is False
    assert coverage["available"]["radiology"] is False


def test_all_three_sources_are_full_multisource() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": True,
                "radiology": True,
            }
        }
    )

    assert coverage["available_count"] == 3
    assert coverage["mode"] == "full_multisource"
    assert coverage["limited"] is False


def test_neutral_source_only_fallback_does_not_claim_risk_is_excluded() -> None:
    risk, summary = _source_only_fallback(["SOURCE_CONTEXT_REVIEW"], "tr")

    assert risk == 1
    assert "risk dışlanamaz" in summary.lower()
    assert "hekim" in summary.lower()


def test_limited_source_suppresses_only_reassuring_low_risk() -> None:
    display_risk, severity, suppressed = _risk_display_for_coverage(
        1,
        {"limited": True},
    )

    assert display_risk is None
    assert severity is None
    assert suppressed is True


def test_limited_source_preserves_actionable_high_risk() -> None:
    display_risk, severity, suppressed = _risk_display_for_coverage(
        3,
        {"limited": True},
    )

    assert display_risk == 3
    assert severity == "high"
    assert suppressed is False
