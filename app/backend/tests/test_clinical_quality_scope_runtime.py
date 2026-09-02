from app.domain import clinical_quality_runtime
from app.domain import clinical_quality_scope_runtime  # noqa: F401


def _metadata(study_date: str, active_date: str):
    return {
        "performed_studies": [
            {
                "canonical_code": "liver_elastography",
                "name": "Karaciğer elastografisi",
                "date": study_date,
                "source_report_id": "report-1",
            }
        ],
        "source_dates": {"laboratory": "2025-12-17", "ultrasound": active_date},
        "recommended_laboratory_tests": [],
        "recommended_imaging_tests": [
            {
                "name": "Karaciğer elastografisi",
                "rationale": "Fibrozis değerlendirmesi için.",
                "priority": "routine",
            }
        ],
    }


def test_historical_study_does_not_suppress_active_case_recommendation() -> None:
    kept_lab, kept_imaging, already = clinical_quality_runtime._filter_recommendations(
        _metadata("2025-01-01", "2026-09-01"),
        [],
    )

    assert kept_lab == []
    assert len(kept_imaging) == 1
    assert already == []


def test_same_date_active_study_is_deduplicated() -> None:
    kept_lab, kept_imaging, already = clinical_quality_runtime._filter_recommendations(
        _metadata("2026-09-01", "2026-09-01"),
        [],
    )

    assert kept_lab == []
    assert kept_imaging == []
    assert len(already) == 1
    assert already[0]["canonical_code"] == "liver_elastography"
