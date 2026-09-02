"""Route deterministic clinical helpers to the domains supported by case evidence.

The clinical-quality layer intentionally contains reusable calculations from several
medical areas. Without routing, every calculation can appear for every patient when
the required laboratory inputs happen to be present. This runtime adds a conservative,
evidence-based relevance gate so a liver-specific score is not shown in a renal case,
for example.

This is *not* a diagnostic classifier. It only decides which deterministic helper
packs are relevant enough to display. The compact AI synthesis still receives the
same bounded source summaries and backend flags as before.
"""

from __future__ import annotations

import contextvars
import re
import unicodedata
from typing import Any

from app.domain import clinical_quality_runtime as quality_runtime
from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


ROUTER_VERSION = "clinical-domain-router-v1.1"

DOMAIN_LABELS: dict[str, str] = {
    "liver": "Karaciğer / hepatobiliyer",
    "hematology_iron": "Hematoloji / demir",
    "metabolic": "Metabolik / glisemik / lipid",
    "renal_urinary": "Böbrek / üriner",
    "thyroid": "Tiroid",
    "inflammation_infection": "Enflamasyon / enfeksiyon",
    "pancreatic": "Pankreas",
    "cardiovascular": "Kardiyovasküler",
    "respiratory": "Solunum",
    "neurologic": "Nörolojik",
    "gastrointestinal": "Gastrointestinal",
    "musculoskeletal": "Kas-iskelet",
    "oncology": "Onkolojik değerlendirme alanı",
}

# Summary terms are deliberately organ/system oriented rather than disease labels.
# A match means "this domain may be relevant", not "the patient has this disease".
DOMAIN_SUMMARY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "liver": (
        "karaciger",
        "hepat",
        "portal ven",
        "portal hipertans",
        "fibroz",
        "siroz",
        "steatoz",
        "elastograf",
        "hepatobilier",
        "safra yolu",
        "kolestaz",
    ),
    "hematology_iron": (
        "anemi",
        "demir eksik",
        "ferritin",
        "transferrin",
        "hematoloji",
        "kanama",
    ),
    "metabolic": (
        "hiperglis",
        "glukoz",
        "diyabet",
        "insulin",
        "metabolik",
        "trigliser",
        "kolesterol",
        "dislipid",
    ),
    "renal_urinary": (
        "bobrek",
        "renal",
        "ureter",
        "mesane",
        "hidronef",
        "nefrolit",
        "tas",
        "idrarda",
        "idrar yolu",
        "proteinuri",
        "hematuri",
    ),
    "thyroid": (
        "tiroid",
        "thyroid",
        "hipotiroid",
        "hipertiroid",
    ),
    "inflammation_infection": (
        "enfeks",
        "inflam",
        "enflam",
        "ates",
        "sepsis",
    ),
    "pancreatic": (
        "pankreas",
        "pancrea",
        "pankreat",
    ),
    "cardiovascular": (
        "kalp",
        "kardiyak",
        "kardiyo",
        "gogus agrisi",
        "carpinti",
        "aritmi",
        "koroner",
        "miyokard",
        "perikard",
    ),
    "respiratory": (
        "akciger",
        "pulmoner",
        "solunum",
        "nefes darligi",
        "dispne",
        "oksuruk",
        "pnonomi",
        "plevra",
    ),
    "neurologic": (
        "noroloj",
        "beyin",
        "bas agrisi",
        "bas donmesi",
        "senkop",
        "nobet",
        "parestezi",
        "gucsuzluk",
    ),
    "gastrointestinal": (
        "mide",
        "bagirsak",
        "gastro",
        "kolon",
        "karin agrisi",
        "ishal",
        "kabizlik",
        "kusma",
        "bulanti",
    ),
    "musculoskeletal": (
        "eklem",
        "kas agrisi",
        "kemik",
        "bel agrisi",
        "boyun agrisi",
        "ortopedi",
        "travma",
    ),
    "oncology": (
        "kitle",
        "tumor",
        "malign",
        "neoplaz",
        "onkoloj",
    ),
}

# Only abnormal/needs-review laboratory observations contribute routing evidence.
# These aliases are for relevance only and are intentionally conservative.
DOMAIN_LAB_ALIASES: dict[str, tuple[str, ...]] = {
    "liver": (
        "ast",
        "alt",
        "ggt",
        "gama glutamil",
        "alkalen fosfataz",
        "alp",
        "bilirubin",
    ),
    "hematology_iron": (
        "ferritin",
        "serum demir",
        "demir",
        "uibc",
        "ddbk",
        "transferrin",
        "hemoglobin",
        "hgb",
        "mcv",
    ),
    "metabolic": (
        "glukoz",
        "glucose",
        "hba1c",
        "hemoglobin a1c",
        "insulin",
        "trigliserid",
        "triglyceride",
        "hdl",
        "ldl",
        "total kolesterol",
        "total cholesterol",
    ),
    "renal_urinary": (
        "kreatinin",
        "creatinine",
        "egfr",
        "ure",
        "urea",
        "bun",
        "idrar",
        "urine",
        "proteinuri",
        "hematuri",
    ),
    "thyroid": (
        "tsh",
        "ft4",
        "free t4",
        "serbest t4",
        "ft3",
        "free t3",
        "serbest t3",
    ),
    "inflammation_infection": (
        "crp",
        "c reaktif protein",
        "sedim",
        "esr",
        "lokosit",
        "leukocyte",
        "wbc",
        "notrofil",
        "neutrophil",
        "prokalsitonin",
        "procalcitonin",
    ),
    "pancreatic": (
        "lipaz",
        "lipase",
        "amilaz",
        "amylase",
    ),
    "cardiovascular": (
        "troponin",
        "nt probnp",
        "bnp",
        "ck mb",
    ),
    "respiratory": (),
    "neurologic": (),
    "gastrointestinal": (),
    "musculoskeletal": (
        "kreatin kinaz",
        "creatine kinase",
        "ck",
    ),
    "oncology": (),
}

SCORE_DOMAIN: dict[str, str] = {
    "FIB4": "liver",
    "APRI": "liver",
    "AST_ALT_RATIO": "liver",
    "TRANSFERRIN_SATURATION": "hematology_iron",
    "TOTAL_HDL_RATIO": "metabolic",
}

CHECK_DOMAINS: dict[str, set[str]] = {
    "SERUM_URINE_GLUCOSE_UNEXPECTED": {"metabolic", "renal_urinary"},
    "IRON_PANEL_INTERNAL_MISMATCH": {"hematology_iron"},
    "ALBUMIN_DENSITY_HEMOCONCENTRATION_CONTEXT": {"renal_urinary"},
}

_DOMAIN_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "medicore_clinical_domain_router_context",
    default=None,
)

_original_generate = ClaudeClinicalHypothesisService.generate_for_analysis_run
_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis
_original_derive_scores = quality_runtime._derive_scores
_original_cross_checks = quality_runtime._cross_checks


def _fold(value: object) -> str:
    text = str(value or "")
    translated = text.translate(
        str.maketrans(
            {
                "ı": "i",
                "İ": "i",
                "ş": "s",
                "Ş": "s",
                "ğ": "g",
                "Ğ": "g",
                "ü": "u",
                "Ü": "u",
                "ö": "o",
                "Ö": "o",
                "ç": "c",
                "Ç": "c",
            }
        )
    )
    normalized = unicodedata.normalize("NFKD", translated)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).strip().lower()


def _status(result: Any) -> str:
    raw = getattr(result, "result_status", None)
    return str(getattr(raw, "value", raw) or "unknown").lower()


def _result_text(result: Any) -> str:
    return _fold(
        " ".join(
            str(item or "")
            for item in (
                getattr(result, "parameter_code", None),
                getattr(result, "canonical_name", None),
                getattr(result, "raw_parameter_name", None),
            )
        )
    )


def _alias_matches(text: str, alias: str) -> bool:
    candidate = _fold(alias)
    if not candidate:
        return False
    padded = f" {text} "
    if len(candidate) <= 5 and " " not in candidate:
        return f" {candidate} " in padded
    return candidate in text


def _source_summary_text(metadata: dict[str, Any]) -> str:
    source_summaries = metadata.get("source_summaries")
    if not isinstance(source_summaries, dict):
        return ""
    values = [
        source_summaries.get("clinical"),
        source_summaries.get("laboratory"),
        source_summaries.get("ultrasound"),
    ]
    return _fold(" ".join(str(item or "") for item in values))


def detect_clinical_domains(
    results: list[Any],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return evidence-backed relevance domains, sorted strongest first.

    Routing threshold is intentionally low for a domain-specific abnormal laboratory
    observation (2 points) or an organ/system phrase in the bounded case summaries
    (3 points). Normal routine-panel values do not activate a domain.
    """

    summary_text = _source_summary_text(metadata)
    domain_entries: list[dict[str, Any]] = []

    for domain_id, label in DOMAIN_LABELS.items():
        score = 0
        evidence: list[str] = []

        for keyword in DOMAIN_SUMMARY_KEYWORDS.get(domain_id, ()):  # strong evidence
            folded_keyword = _fold(keyword)
            if folded_keyword and folded_keyword in summary_text:
                score += 3
                evidence.append(f"Kaynak özeti: {keyword}")
                if len(evidence) >= 4:
                    break

        abnormal_hits = 0
        for result in results:
            if _status(result) not in {"high", "low", "needs_review"}:
                continue
            text = _result_text(result)
            if not text:
                continue
            if any(
                _alias_matches(text, alias)
                for alias in DOMAIN_LAB_ALIASES.get(domain_id, ())
            ):
                abnormal_hits += 1
                score += 2
                name = (
                    getattr(result, "canonical_name", None)
                    or getattr(result, "raw_parameter_name", None)
                    or getattr(result, "parameter_code", None)
                    or "laboratuvar bulgusu"
                )
                evidence.append(f"Referans dışı laboratuvar: {name}")
                if abnormal_hits >= 3:
                    break

        if score >= 2:
            domain_entries.append(
                {
                    "id": domain_id,
                    "label": label,
                    "score": score,
                    "evidence": evidence[:6],
                    "reason": "Vaka kaynaklarında bu klinik alan için ilgili bulgu var.",
                }
            )

    domain_entries.sort(key=lambda item: (-int(item["score"]), str(item["id"])))
    return domain_entries


def _domain_ids(domains: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("id"))
        for item in domains
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def filter_scores_for_domains(
    scores: list[dict[str, Any]],
    domains: set[str],
) -> list[dict[str, Any]]:
    """Keep only calculations whose clinical domain has case evidence."""

    kept: list[dict[str, Any]] = []
    for score in scores:
        code = str(score.get("code") or "")
        required_domain = SCORE_DOMAIN.get(code)
        if required_domain is None or required_domain in domains:
            kept.append(score)
    return kept


def filter_checks_for_domains(
    checks: list[dict[str, Any]],
    domains: set[str],
) -> list[dict[str, Any]]:
    """Keep known cross-checks only when one of their relevance domains is active."""

    kept: list[dict[str, Any]] = []
    for check in checks:
        code = str(check.get("code") or "")
        required_domains = CHECK_DOMAINS.get(code)
        if required_domains is None or required_domains.intersection(domains):
            kept.append(check)
    return kept


def _derive_scores_routed(results: list[Any], patient_age: float | None):
    scores = _original_derive_scores(results, patient_age)
    context = _DOMAIN_CONTEXT.get()
    if not context:
        return scores
    return filter_scores_for_domains(scores, set(context.get("domain_ids") or set()))


def _cross_checks_routed(results: list[Any]):
    checks = _original_cross_checks(results)
    context = _DOMAIN_CONTEXT.get()
    if not context:
        return checks
    return filter_checks_for_domains(checks, set(context.get("domain_ids") or set()))


async def _generate_with_domain_router(
    self: ClaudeClinicalHypothesisService,
    analysis_run_id: Any,
    request: Any,
):
    # One additional read is intentional: routing needs the abnormal result names
    # before the quality wrapper chooses which deterministic helpers to emit.
    results = list(await self._lab_results.list_for_analysis_run(analysis_run_id))
    metadata = dict(request.metadata_json or {})
    domains = detect_clinical_domains(results, metadata)
    domain_ids = _domain_ids(domains)

    metadata["clinical_domains"] = domains
    metadata["clinical_domain_router"] = {
        "version": ROUTER_VERSION,
        "mode": "evidence_relevance_not_diagnosis",
        "active_domain_ids": sorted(domain_ids),
    }
    enriched_request = request.model_copy(update={"metadata_json": metadata})

    token = _DOMAIN_CONTEXT.set(
        {
            "domains": domains,
            "domain_ids": domain_ids,
        }
    )
    try:
        return await _original_generate(self, analysis_run_id, enriched_request)
    finally:
        _DOMAIN_CONTEXT.reset(token)


def _build_hypothesis_with_domain_router(self: ClaudeClinicalHypothesisService, *args, **kwargs):
    hypothesis = _original_build_hypothesis(self, *args, **kwargs)
    context = _DOMAIN_CONTEXT.get()
    if not context:
        return hypothesis

    metadata = dict(hypothesis.metadata_json or {})
    domains = list(context.get("domains") or [])
    domain_ids = set(context.get("domain_ids") or set())
    metadata["clinical_domains"] = domains
    metadata["clinical_domain_router"] = {
        "version": ROUTER_VERSION,
        "mode": "evidence_relevance_not_diagnosis",
        "active_domain_ids": sorted(domain_ids),
        "note": (
            "Bu alanlar tanı değildir; yalnızca hangi deterministik hesap ve çapraz "
            "kontrollerin vaka için gösterileceğini sınırlar."
        ),
    }
    hypothesis.metadata_json = metadata
    return hypothesis


# The quality wrapper looks up these module globals at call time, so replacing them
# here changes only display/relevance selection while preserving the tested formulas.
quality_runtime._derive_scores = _derive_scores_routed
quality_runtime._cross_checks = _cross_checks_routed

# Install after clinical_quality_runtime and clinical_quality_scope_runtime.
ClaudeClinicalHypothesisService.generate_for_analysis_run = _generate_with_domain_router
ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_domain_router
