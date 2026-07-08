"""AliasEngine.

Safe alias resolver with curated Turkish/English lab synonyms.

Important fix:
- If a known curated raw name cannot be mapped to an existing DB parameter,
  it returns UNKNOWN instead of falling through to risky fuzzy matching.
  This prevents examples like Vitamin B1 -> Vitamin B12 or Triglyceride -> IG%.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from app.domain.normalization import normalize_alias
from app.infrastructure.database.repositories.clinical_parameter_repository import (
    ClinicalParameterRepository,
)
from app.infrastructure.database.repositories.parameter_alias_repository import (
    ParameterAliasRepository,
)
from app.schemas.analysis import AliasCandidate, AliasMatchResult, MatchMethod


CONF_PARAMETER_CODE = 1.0
CONF_CANONICAL_NAME = 0.99
CONF_CURATED_ALIAS = 0.94
ALIAS_AUTO_ACCEPT = 0.90
FUZZY_AUTO_ACCEPT = 0.95
FUZZY_REVIEW_FLOOR = 0.75
MAX_ALTERNATIVES = 3
_MIN_FUZZY_LENGTH = 2


_CURATED_ALIAS_TARGETS_RAW: dict[str, tuple[str, ...]] = {
    # Kidney / glucose
    "BUN": ("BUN", "Blood Urea Nitrogen"),
    "Kreatinin": ("Creatinine", "Kreatinin", "CREA"),
    "GFR": ("GFR", "eGFR", "Glomerular Filtration Rate"),
    "Glukoz": ("Glucose", "Glukoz", "Fasting Glucose"),

    # Lipids
    "Total Kolesterol": ("Total Cholesterol", "Cholesterol", "Total Kolesterol"),
    "HDL": ("HDL", "HDL Cholesterol"),
    "Trigliserit": ("Triglyceride", "Triglycerides", "Trigliserit"),
    "LDL": ("LDL", "LDL Cholesterol"),
    "Non-HDL": ("Non-HDL Cholesterol", "Non HDL Cholesterol"),

    # Liver / bilirubin
    "ALP": ("ALP", "Alkaline Phosphatase"),
    "AST": ("AST", "SGOT"),
    "ALT": ("ALT", "SGPT"),
    "GGT": ("GGT", "Gamma GT", "Gama-GT"),
    "Total Bilirubin": ("Total Bilirubin", "Bilirubin Total"),
    "Direkt Bilirubin": ("Direct Bilirubin", "Bilirubin Direct"),

    # Thyroid / vitamins / inflammation
    "FT3": ("FT3", "Free T3"),
    "FT4": ("FT4", "Free T4"),
    "TSH": ("TSH", "Thyroid Stimulating Hormone"),
    "Vitamin B12": ("Vitamin B12", "B12"),
    "Vitamin D": ("Vitamin D", "25-OH Vitamin D", "25 OH Vitamin D"),
    "Vitamin B1": ("Vitamin B1", "Thiamine", "B1"),
    "Sedimentasyon": ("ESR", "Sedimentation Rate", "Sedimantasyon"),
    "CRP": ("CRP", "C-Reactive Protein"),
    "Folik Asit": ("Folate", "Folic Acid", "Folik Asit"),

    # CBC
    "Lökosit": ("WBC", "Lökosit", "Lokosit", "Leukocyte"),
    "Eritrosit": ("RBC", "Eritrosit", "Erythrocyte"),
    "Hemoglobin": ("Hemoglobin", "HGB", "Hb"),
    "Hematokrit": ("Hematokrit", "Hematocrit", "HCT"),
    "MCV": ("MCV",),
    "MCH": ("MCH",),
    "MCHC": ("MCHC",),
    "RDW-CV": ("RDW-CV", "RDW", "RDW CV"),
    "Trombosit": ("Platelet", "Trombosit", "PLT"),
    "MPV": ("MPV",),
    "PCT": ("PCT", "Plateletcrit"),
    "P-LCR": ("P-LCR", "Platelet Large Cell Ratio"),

    # Differential absolute + percentages. Keep absolute and percentage
    # separate; if DB lacks absolute entries, better UNKNOWN than wrong % mapping.
    "Nötrofil": ("Neutrophil", "Nötrofil", "Notrofil", "NEU", "NEUT"),
    "Nötrofil %": ("Neutrophil %", "Nötrofil %", "Notrofil %", "NEU%", "NEUT%"),
    "Lenfosit": ("Lymphocyte", "Lenfosit", "LYM", "LYMPH"),
    "Lenfosit %": ("Lymphocyte %", "Lenfosit %", "LYM%", "LYMPH%"),
    "Monosit": ("Monocyte", "Monosit", "MON", "MONO"),
    "Monosit %": ("Monocyte %", "Monosit %", "MON%", "MONO%"),
    "Eozinofil": ("Eosinophil", "Eozinofil", "EOS", "EO"),
    "Eozinofil %": ("Eosinophil %", "Eozinofil %", "EOS%", "EO%"),
    "Bazofil": ("Basophil", "Bazofil", "BAS", "BASO"),
    "Bazofil %": ("Basophil %", "Bazofil %", "BAS%", "BASO%"),
    "IG": ("IG", "Immature Granulocyte"),
    "IG %": ("IG %", "Immature Granulocyte %"),
}

_CURATED_ALIAS_TARGETS = {
    normalize_alias(raw): tuple(targets)
    for raw, targets in _CURATED_ALIAS_TARGETS_RAW.items()
}


class _IndexEntry:
    __slots__ = ("parameter_id", "parameter_code", "canonical_name", "normalized")

    def __init__(self, parameter_id, parameter_code, canonical_name, normalized):
        self.parameter_id = parameter_id
        self.parameter_code = parameter_code
        self.canonical_name = canonical_name
        self.normalized = normalized


class AliasEngine:
    def __init__(
        self,
        parameter_repository: ClinicalParameterRepository,
        alias_repository: ParameterAliasRepository,
    ) -> None:
        self._parameters = parameter_repository
        self._aliases = alias_repository
        self._entries: list[_IndexEntry] = []
        self._by_normalized: dict[str, _IndexEntry] = {}
        self._by_code: dict[str, _IndexEntry] = {}
        self._loaded = False

    async def refresh(self) -> None:
        parameters = await self._parameters.list_all()
        self._entries = []
        self._by_normalized = {}
        self._by_code = {}

        for parameter in parameters:
            entry = _IndexEntry(
                parameter_id=parameter.id,
                parameter_code=parameter.parameter_code,
                canonical_name=parameter.canonical_name,
                normalized=normalize_alias(parameter.canonical_name),
            )
            self._entries.append(entry)
            self._by_code[parameter.parameter_code] = entry
            self._by_code[parameter.parameter_code.upper()] = entry

            if entry.normalized:
                self._by_normalized.setdefault(entry.normalized, entry)

        self._loaded = True

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            await self.refresh()

    async def resolve(self, raw_parameter_name: str) -> AliasMatchResult:
        raw = (raw_parameter_name or "").strip()
        if not raw:
            return AliasMatchResult.unknown(raw_parameter_name or "")

        await self._ensure_loaded()

        entry = self._by_code.get(raw) or self._by_code.get(raw.upper())
        if entry is not None:
            return self._result(raw, entry, CONF_PARAMETER_CODE, MatchMethod.PARAMETER_CODE, False)

        normalized = normalize_alias(raw)

        entry = self._by_normalized.get(normalized)
        if entry is not None:
            return self._result(raw, entry, CONF_CANONICAL_NAME, MatchMethod.CANONICAL_NAME, False)

        is_curated_name = normalized in _CURATED_ALIAS_TARGETS
        entry = self._curated_alias_resolve(normalized)
        if entry is not None:
            return self._result(raw, entry, CONF_CURATED_ALIAS, MatchMethod.NORMALIZED_ALIAS, False)

        # Known curated names should not be fuzzy-mapped to a wrong parameter.
        if is_curated_name:
            return AliasMatchResult.unknown(raw)

        alias = await self._aliases.resolve(raw)
        if alias is not None:
            param = await self._parameters.get_by_id(alias.canonical_parameter_id)
            if param is not None:
                confidence = float(alias.confidence)
                needs_review = confidence < ALIAS_AUTO_ACCEPT
                return AliasMatchResult(
                    raw_parameter_name=raw,
                    canonical_parameter_id=param.id,
                    parameter_code=param.parameter_code,
                    canonical_name=param.canonical_name,
                    confidence=confidence,
                    match_method=MatchMethod.NORMALIZED_ALIAS,
                    needs_review=needs_review,
                )

        return self._fuzzy_resolve(raw, normalized)

    async def resolve_many(self, raw_names: list[str]) -> list[AliasMatchResult]:
        await self._ensure_loaded()
        return [await self.resolve(name) for name in raw_names]

    def _curated_alias_resolve(self, normalized: str) -> _IndexEntry | None:
        targets = _CURATED_ALIAS_TARGETS.get(normalized)
        if not targets:
            return None

        for target in targets:
            entry = self._by_code.get(target) or self._by_code.get(target.upper())
            if entry is not None:
                return entry

            entry = self._by_normalized.get(normalize_alias(target))
            if entry is not None:
                return entry

        return None

    def _fuzzy_resolve(self, raw: str, normalized: str) -> AliasMatchResult:
        if len(normalized) < _MIN_FUZZY_LENGTH or not self._entries:
            return AliasMatchResult.unknown(raw)

        scored = sorted(
            (
                (SequenceMatcher(None, normalized, e.normalized).ratio(), e)
                for e in self._entries
                if e.normalized
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not scored:
            return AliasMatchResult.unknown(raw)

        best_ratio, best_entry = scored[0]
        alternatives = [
            AliasCandidate(
                parameter_id=e.parameter_id,
                parameter_code=e.parameter_code,
                canonical_name=e.canonical_name,
                similarity=round(ratio, 4),
            )
            for ratio, e in scored[:MAX_ALTERNATIVES]
            if ratio >= FUZZY_REVIEW_FLOOR
        ]

        if best_ratio >= FUZZY_AUTO_ACCEPT:
            return AliasMatchResult(
                raw_parameter_name=raw,
                canonical_parameter_id=best_entry.parameter_id,
                parameter_code=best_entry.parameter_code,
                canonical_name=best_entry.canonical_name,
                confidence=round(best_ratio, 4),
                match_method=MatchMethod.FUZZY,
                needs_review=False,
                alternatives=alternatives,
            )

        if best_ratio >= FUZZY_REVIEW_FLOOR:
            return AliasMatchResult(
                raw_parameter_name=raw,
                canonical_parameter_id=best_entry.parameter_id,
                parameter_code=best_entry.parameter_code,
                canonical_name=best_entry.canonical_name,
                confidence=round(best_ratio, 4),
                match_method=MatchMethod.FUZZY,
                needs_review=True,
                alternatives=alternatives,
            )

        return AliasMatchResult.unknown(raw, alternatives=alternatives)

    @staticmethod
    def _result(
        raw: str,
        entry: _IndexEntry,
        confidence: float,
        method: MatchMethod,
        needs_review: bool,
    ) -> AliasMatchResult:
        return AliasMatchResult(
            raw_parameter_name=raw,
            canonical_parameter_id=entry.parameter_id,
            parameter_code=entry.parameter_code,
            canonical_name=entry.canonical_name,
            confidence=confidence,
            match_method=method,
            needs_review=needs_review,
        )