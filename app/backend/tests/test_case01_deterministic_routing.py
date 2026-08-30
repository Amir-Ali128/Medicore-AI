from app.api.routes import lab_case01_safety
from app.domain.claude_clinical_hypothesis_service import (
    ClaudeClinicalHypothesisService,
)


def test_case01_aliases_cover_unmapped_labels() -> None:
    normalized = lab_case01_safety.alias_engine.normalize_alias
    targets = lab_case01_safety.alias_engine._CURATED_ALIAS_TARGETS

    assert normalized("KAN ÜRE NİTROJENİ (BUN)") in targets
    assert normalized("BICARBONATE (HCO3)") in targets
    assert normalized("ANION GAP") in targets


def test_case01_reference_specs_are_deterministic() -> None:
    specs = {item[0]: item for item in lab_case01_safety._PARAMETER_SPECS}

    assert specs["BUN"][3:] == (7.0, 20.0)
    assert specs["HCO3"][3:] == (22.0, 26.0)
    assert specs["ANION_GAP"][3:] == (8.0, 16.0)


def test_prerenal_pattern_requires_labs_and_dehydration_symptoms() -> None:
    flags = ["BUN_HIGH", "KREATININ_HIGH", "GFR_LOW", "SODYUM_HIGH"]
    symptoms = ["2 gündür kusma", "48 saattir sıvı alımı azalmış", "ağız kuruluğu"]

    assert lab_case01_safety.should_add_prerenal_pattern(flags, symptoms) is True
    assert lab_case01_safety.should_add_prerenal_pattern(flags, []) is False


def test_compact_prompt_adds_backend_pattern_without_raw_values() -> None:
    flags = ["BUN_HIGH", "KREATININ_HIGH", "GFR_LOW"]
    symptoms = ["Kusma ve azalmış sıvı alımı"]

    prompt = ClaudeClinicalHypothesisService._build_user_prompt(symptoms, flags, "tr")

    assert "DEHYDRATION_SYMPTOMS" in flags
    assert "PRERENAL_DEHYDRATION_PATTERN_REVIEW" in flags
    assert "PRERENAL_DEHYDRATION_PATTERN_REVIEW" in prompt
    assert "68" not in prompt
    assert "1.4" not in prompt
    assert "7-20" not in prompt


def test_prerenal_fallback_is_short_and_physician_review_only() -> None:
    risk, summary = ClaudeClinicalHypothesisService._fallback_output(
        ["BUN_HIGH", "PRERENAL_DEHYDRATION_PATTERN_REVIEW"],
        "tr",
    )

    assert risk == 2
    assert len(summary) <= 120
    assert "hekim değerlendirmesi" in summary
