from app.domain.pathological_findings_runtime import _pathological_findings


def test_high_and_low_findings_include_reference_reason() -> None:
    evidence = [
        {
            "parameter_name": "ALT",
            "result_status": "high",
            "value": "55",
            "unit": "U/L",
            "reference_min": "-1000000000",
            "reference_max": "50",
            "classification_reason": "backend reason",
        },
        {
            "parameter_name": "HDL kolesterol",
            "result_status": "low",
            "value": "30",
            "unit": "mg/dL",
            "reference_min": "40",
            "reference_max": "1000000000",
            "classification_reason": "backend reason",
        },
    ]

    findings = _pathological_findings(evidence, [])

    assert len(findings) == 2
    assert findings[0]["reference_text"] == "< 50 U/L"
    assert "üst sınırı 50 U/L" in findings[0]["classification_reason"]
    assert findings[1]["reference_text"] == "> 40 mg/dL"
    assert "alt sınırı 40 mg/dL" in findings[1]["classification_reason"]
