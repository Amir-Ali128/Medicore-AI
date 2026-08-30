from app.domain.pathological_findings_runtime import _pathological_findings


def test_only_deterministic_high_low_are_pathological() -> None:
    evidence = [
        {
            "parameter_name": "Sodyum",
            "value": "147",
            "unit": "mmol/L",
            "result_status": "high",
        },
        {
            "parameter_name": "eGFR",
            "value": "58",
            "unit": "mL/dk/1.73m2",
            "result_status": "low",
        },
        {
            "parameter_name": "Anion Gap",
            "value": "16",
            "unit": "mEq/L",
            "result_status": "normal",
        },
        {
            "parameter_name": "Eşlenemeyen Test",
            "value": "5",
            "unit": None,
            "result_status": "unknown",
        },
        {
            "parameter_name": "İnceleme Gereken Test",
            "value": "4",
            "unit": None,
            "result_status": "needs_review",
        },
    ]

    findings = _pathological_findings(evidence, [])

    assert [item["name"] for item in findings] == ["Sodyum", "eGFR"]
    assert findings[0]["display"] == "Sodyum: 147 mmol/L (yüksek)"
    assert findings[1]["display"] == "eGFR: 58 mL/dk/1.73m2 (düşük)"


def test_vital_flags_are_exposed_without_raw_values() -> None:
    findings = _pathological_findings(
        [],
        [
            "BLOOD_PRESSURE_HIGH",
            "OXYGEN_SATURATION_LOW",
            "PRERENAL_DEHYDRATION_PATTERN_REVIEW",
        ],
    )

    assert [item["name"] for item in findings] == [
        "Kan basıncı",
        "Oksijen satürasyonu",
    ]
    assert all(item["value"] is None for item in findings)
    assert all(item["source"] == "vital" for item in findings)
