"""Production startup must install a fixed clinical runtime and safe AI wording.

Regression: the uncertainty/physician-review layers were never imported by the
application, and another layer was imported lazily by the first source-only
request, so the system prompt depended on request order.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.domain import claude_clinical_hypothesis_service as service_module

_BACKEND = Path(__file__).resolve().parents[1]


_CASES = {
    "definitive_tr": ("Hipernatremi ve dehidratasyon", "tr"),
    "possible_tr": ("Prerenal patern olabilir; hekim değerlendirmesi gerekir.", "tr"),
    "definitive_en": ("Acute kidney injury", "en"),
    "blocked_tr": ("Kesin tanı: sepsis", "tr"),
}


def _production_state() -> dict:
    """Import only app.main in a clean interpreter, as the server does."""
    code = (
        "import json, sys\n"
        f"CASES = {_CASES!r}\n"
        "import app.main\n"
        "from app.domain import claude_clinical_hypothesis_service as s\n"
        "C = s.ClaudeClinicalHypothesisService\n"
        "before = s._SYSTEM_PROMPT\n"
        "import app.domain.source_only_case_evaluation\n"
        "from app.domain.clinical_domain_router_runtime import detect_clinical_domains\n"
        "print(json.dumps({\n"
        "  'prompt': before,\n"
        "  'prompt_after_lazy_import': s._SYSTEM_PROMPT,\n"
        "  'router_loaded': 'app.domain.clinical_domain_router_runtime' in sys.modules,\n"
        "  'summary': C._parse_compact_output({'risk': 2, 'summary': 'Akut böbrek hasarı'},"
        " flags=[], language='tr')[1],\n"
        "  'user_prompt': json.loads(C._build_user_prompt(['halsizlik'], ['FLAG'], 'tr')),\n"
        "  'max_chars': s._MAX_SUMMARY_CHARS,\n"
        "  'parsed': {key: C._parse_compact_output({'risk': 2, 'summary': text}, flags=[], language=lang)[1]\n"
        "             for key, (text, lang) in CASES.items()},\n"
        "}))\n"
    )
    output = subprocess.run(
        [sys.executable, "-c", code], cwd=_BACKEND, capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()[-1]
    return json.loads(output)


def test_production_prompt_is_fixed_and_requires_possibility_language() -> None:
    state = _production_state()
    prompt = state["prompt"].lower()

    assert state["router_loaded"]
    assert state["prompt"] == state["prompt_after_lazy_import"]
    assert "olabilir" in prompt
    assert "physician review is required" in prompt
    assert "hekim değerlendirmesi gerekir" in prompt


def test_production_summary_is_forced_to_possibility_language() -> None:
    summary = _production_state()["summary"]

    assert "olabilir" in summary
    assert "hekim değerlendirmesi gerekir" in summary


def test_production_user_prompt_has_no_empty_summaries_key() -> None:
    assert "summaries" not in _production_state()["user_prompt"]


def test_parser_adds_uncertainty_to_definitive_turkish_summary() -> None:
    state = _production_state()
    summary = state["parsed"]["definitive_tr"]

    assert summary.endswith("olabilir; hekim değerlendirmesi gerekir.")
    assert len(summary) <= state["max_chars"]


def test_parser_preserves_existing_possibility_wording() -> None:
    parsed = _production_state()["parsed"]

    assert parsed["possible_tr"] == _CASES["possible_tr"][0]


def test_parser_adds_uncertainty_to_english_summary() -> None:
    summary = _production_state()["parsed"]["definitive_en"]

    assert "may" in summary
    assert "physician review is required" in summary


def test_blocked_language_still_uses_deterministic_fallback() -> None:
    summary = _production_state()["parsed"]["blocked_tr"]

    assert summary == "Backend bulguları doktor değerlendirmesi gerektiriyor."


def test_guard_respects_configured_summary_limit() -> None:
    long_text = "Uzun klinik özet " * 40

    guarded = service_module.ensure_possibility_language(long_text, "tr", 120)

    assert len(guarded) <= 120
    assert guarded.endswith("olabilir; hekim değerlendirmesi gerekir.")
