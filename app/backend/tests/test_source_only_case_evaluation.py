from app.domain.source_only_case_evaluation import (
    _source_only_fallback,
    source_coverage,
)


def test_clinical_only_is_single_source() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": False,
                "ultrasound": False,
            },
            "source_summaries": {
                "clinical": "Baş ağrısı",
                "laboratory": "",
                "ultrasound": "",
            },
        }
    )

    assert coverage["available_count"] == 1
    assert coverage["mode"] == "single_source"
    assert coverage["limited"] is True
    assert coverage["available"] == {
        "clinical": True,
        "laboratory": False,
        "ultrasound": False,
    }


def test_clinical_and_ultrasound_is_partial_multisource() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": False,
                "ultrasound": True,
            }
        }
    )

    assert coverage["available_count"] == 2
    assert coverage["mode"] == "partial_multisource"
    assert coverage["limited"] is True


def test_summary_fallback_supports_older_callers() -> None:
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
    assert coverage["available"]["ultrasound"] is True


def test_explicit_false_cannot_be_overridden_by_placeholder_summary() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": False,
                "ultrasound": False,
            },
            "source_summaries": {
                "clinical": "Baş ağrısı",
                "laboratory": "Laboratuvar verisi bulunamadı.",
                "ultrasound": "Ultrason sonucu bulunamadı.",
            },
        }
    )

    assert coverage["available_count"] == 1
    assert coverage["available"]["laboratory"] is False
    assert coverage["available"]["ultrasound"] is False


def test_all_three_sources_are_full_multisource() -> None:
    coverage = source_coverage(
        {
            "source_availability": {
                "clinical": True,
                "laboratory": True,
                "ultrasound": True,
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
