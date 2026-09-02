from types import SimpleNamespace

from app.domain import clinical_domain_router_runtime as router
from app.domain import clinical_quality_runtime as quality


def _result(name: str, value: float, *, status: str = "normal"):
    return SimpleNamespace(
        raw_parameter_name=name,
        canonical_name=name,
        parameter_code=name,
        normalized_value=value,
        raw_value=str(value),
        unit="",
        reference_min=None,
        reference_max=40 if name == "AST" else None,
        result_status=status,
        measured_at=None,
        rule_applied="test_rule",
    )


def _metadata(*, clinical: str = "", laboratory: str = "", ultrasound: str = ""):
    return {
        "source_summaries": {
            "clinical": clinical,
            "laboratory": laboratory,
            "ultrasound": ultrasound,
        }
    }


def test_liver_case_activates_liver_domain() -> None:
    results = [
        _result("AST", 55, status="high"),
        _result("ALT", 70, status="high"),
        _result("PLT", 130, status="low"),
    ]
    domains = router.detect_clinical_domains(
        results,
        _metadata(ultrasound="Karaciğer elastografisinde fibrozis açısından değerlendirme."),
    )

    ids = {item["id"] for item in domains}
    assert "liver" in ids


def test_renal_case_does_not_activate_liver_from_normal_routine_labs() -> None:
    results = [
        _result("AST", 28, status="normal"),
        _result("ALT", 31, status="normal"),
        _result("PLT", 240, status="normal"),
        _result("Kreatinin", 1.8, status="high"),
        _result("İdrar · Eritrosit", 20, status="high"),
    ]
    domains = router.detect_clinical_domains(
        results,
        _metadata(
            clinical="Yan ağrısı",
            ultrasound="Sol böbrekte taş ve hafif hidronefroz izlenmiştir.",
        ),
    )

    ids = {item["id"] for item in domains}
    assert "renal_urinary" in ids
    assert "liver" not in ids


def test_renal_domain_filters_out_liver_specific_scores() -> None:
    all_scores = [
        {"code": "FIB4"},
        {"code": "APRI"},
        {"code": "AST_ALT_RATIO"},
        {"code": "TRANSFERRIN_SATURATION"},
        {"code": "TOTAL_HDL_RATIO"},
    ]

    routed = router.filter_scores_for_domains(all_scores, {"renal_urinary"})

    assert routed == []


def test_multidomain_case_keeps_only_relevant_score_packs() -> None:
    all_scores = [
        {"code": "FIB4"},
        {"code": "APRI"},
        {"code": "AST_ALT_RATIO"},
        {"code": "TRANSFERRIN_SATURATION"},
        {"code": "TOTAL_HDL_RATIO"},
    ]

    routed = router.filter_scores_for_domains(
        all_scores,
        {"liver", "metabolic"},
    )

    assert [item["code"] for item in routed] == [
        "FIB4",
        "APRI",
        "AST_ALT_RATIO",
        "TOTAL_HDL_RATIO",
    ]


def test_iron_and_glucose_cross_checks_are_domain_scoped() -> None:
    checks = [
        {"code": "SERUM_URINE_GLUCOSE_UNEXPECTED"},
        {"code": "IRON_PANEL_INTERNAL_MISMATCH"},
        {"code": "ALBUMIN_DENSITY_HEMOCONCENTRATION_CONTEXT"},
        {"code": "FUTURE_GENERIC_CHECK"},
    ]

    metabolic = router.filter_checks_for_domains(checks, {"metabolic"})
    assert [item["code"] for item in metabolic] == [
        "SERUM_URINE_GLUCOSE_UNEXPECTED",
        "FUTURE_GENERIC_CHECK",
    ]

    renal = router.filter_checks_for_domains(checks, {"renal_urinary"})
    assert [item["code"] for item in renal] == [
        "SERUM_URINE_GLUCOSE_UNEXPECTED",
        "ALBUMIN_DENSITY_HEMOCONCENTRATION_CONTEXT",
        "FUTURE_GENERIC_CHECK",
    ]


def test_router_preserves_existing_formula_engine_outside_request_context() -> None:
    results = [
        _result("AST", 45, status="high"),
        _result("ALT", 55, status="high"),
        _result("PLT", 110, status="low"),
    ]
    # Importing the router monkey-patches quality._derive_scores, but without an
    # active request context it must preserve backwards-compatible direct behavior.
    scores = {item["code"]: item for item in quality._derive_scores(results, 50)}
    assert "FIB4" in scores
    assert "APRI" in scores
