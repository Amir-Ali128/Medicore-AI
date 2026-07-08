"""Phase 1 active-parameter selection.

Single source of truth for deciding which imported CSV parameters are *active*
in Phase 1. Phase 1 covers exactly four clinical groups:

    - Anemia
    - Diabetes / Prediabetes
    - Thyroid
    - Liver Function

A parameter is activated only when its (normalized) name matches one of the
curated aliases below. Matching is exact on the normalized key, which keeps
near-miss neighbours passive on purpose — e.g. urine glucose ("İdrar Glukoz"),
pre-albumin, the bone ALP isoenzyme, Total T3/T4, and thyroglobulin are NOT
activated. Everything not matched here stays a passive dictionary record
(active_phase1=False, analysis_level=L0).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import AnalysisLevel
from app.domain.normalization import normalize_alias, strip_parenthetical

# Human-readable group labels (kept stable; used for provenance/metadata).
GROUP_ANEMIA = "Anemia"
GROUP_DIABETES = "Diabetes / Prediabetes"
GROUP_THYROID = "Thyroid"
GROUP_LIVER = "Liver Function"

# Analysis levels applied by the selector.
ACTIVE_LEVEL = AnalysisLevel.L4
PASSIVE_LEVEL = AnalysisLevel.L0


@dataclass(frozen=True, slots=True)
class Phase1Definition:
    """A single canonical parameter that is active in Phase 1."""

    group: str
    code: str
    canonical_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Phase1Match:
    """Result of matching a raw parameter name to a Phase 1 definition."""

    group: str
    code: str
    canonical_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    analysis_level: AnalysisLevel = field(default=ACTIVE_LEVEL)
    active_phase1: bool = field(default=True)


# --- Curated Phase 1 definitions ----------------------------------------
# Aliases include both the Turkish source-of-truth names and common English /
# abbreviation variants so the same table also seeds the alias dictionary.
_DEFINITIONS: tuple[Phase1Definition, ...] = (
    # -- Anemia ----------------------------------------------------------
    Phase1Definition(GROUP_ANEMIA, "HGB", "Hemoglobin", ("Hemoglobin", "HGB", "Hb")),
    Phase1Definition(GROUP_ANEMIA, "HCT", "Hematokrit", ("Hematokrit", "HCT", "Hematocrit")),
    Phase1Definition(GROUP_ANEMIA, "RBC", "Eritrosit", ("Eritrosit", "RBC", "Erythrocyte", "Kırmızı Kan Hücresi")),
    Phase1Definition(GROUP_ANEMIA, "MCV", "MCV", ("MCV", "Ortalama Eritrosit Hacmi")),
    Phase1Definition(GROUP_ANEMIA, "MCH", "MCH", ("MCH", "Ortalama Eritrosit Hemoglobini")),
    Phase1Definition(GROUP_ANEMIA, "MCHC", "MCHC", ("MCHC",)),
    Phase1Definition(GROUP_ANEMIA, "FERRITIN", "Ferritin", ("Ferritin",)),
    Phase1Definition(GROUP_ANEMIA, "IRON", "Demir", ("Demir", "Serum Demir", "Serum Iron", "Iron")),
    Phase1Definition(GROUP_ANEMIA, "TIBC", "TIBC", ("TIBC", "Total Demir Bağlama Kapasitesi", "Total Iron Binding Capacity")),
    # -- Diabetes / Prediabetes -----------------------------------------
    Phase1Definition(GROUP_DIABETES, "GLU", "Glukoz", ("Glukoz", "Açlık Glukoz", "Fasting Glucose", "Glucose", "Kan Şekeri")),
    Phase1Definition(GROUP_DIABETES, "HBA1C", "HbA1c", ("HbA1c", "A1c", "Glike Hemoglobin", "Hemoglobin A1c")),
    Phase1Definition(GROUP_DIABETES, "CPEP", "C-Peptid", ("C-Peptid", "C-Peptide", "C Peptid", "C Peptide")),
    Phase1Definition(GROUP_DIABETES, "GLU_PP", "Postprandial Glucose", ("Postprandial Glucose", "Postprandiyal Glukoz", "Tokluk Glukoz", "Tokluk Kan Şekeri", "PP Glukoz", "2. Saat Glukoz")),
    Phase1Definition(GROUP_DIABETES, "INSULIN", "İnsülin", ("İnsülin", "Insülin", "Insulin")),
    Phase1Definition(GROUP_DIABETES, "HOMA_IR", "HOMA-IR", ("HOMA-IR", "HOMA IR", "HOMA", "HOMA-Insülin Direnci", "İnsülin Direnci (HOMA)")),
    # -- Thyroid ---------------------------------------------------------
    Phase1Definition(GROUP_THYROID, "TSH", "TSH", ("TSH", "Tiroid Stimülan Hormon", "Thyroid Stimulating Hormone")),
    Phase1Definition(GROUP_THYROID, "FT3", "Serbest T3", ("Serbest T3", "Free T3", "sT3", "FT3")),
    Phase1Definition(GROUP_THYROID, "FT4", "Serbest T4", ("Serbest T4", "Free T4", "sT4", "FT4")),
    Phase1Definition(GROUP_THYROID, "ATPO", "Anti-TPO", ("Anti-TPO", "Anti TPO", "Antitiroid Peroksidaz", "TPO Antikoru")),
    Phase1Definition(GROUP_THYROID, "ATG", "Anti-TG", ("Anti-TG", "Anti TG", "Antitiroglobulin", "Tiroglobulin Antikoru")),
    Phase1Definition(GROUP_THYROID, "RT3", "Reverse T3", ("Reverse T3", "rT3", "Ters T3", "Reverse T3 (rT3)")),
    # -- Liver Function --------------------------------------------------
    Phase1Definition(GROUP_LIVER, "ALT", "ALT", ("ALT", "Alanin Aminotransferaz", "SGPT", "ALAT")),
    Phase1Definition(GROUP_LIVER, "AST", "AST", ("AST", "Aspartat Aminotransferaz", "SGOT", "ASAT")),
    Phase1Definition(GROUP_LIVER, "GGT", "GGT", ("GGT", "Gama Glutamil Transferaz", "GGTP")),
    Phase1Definition(GROUP_LIVER, "ALP", "ALP", ("ALP", "Alkalen Fosfataz", "Alkaline Phosphatase")),
    Phase1Definition(GROUP_LIVER, "TBIL", "Total Bilirubin", ("Total Bilirubin", "Toplam Bilirubin", "Bilirubin Total")),
    Phase1Definition(GROUP_LIVER, "DBIL", "Direkt Bilirubin", ("Direkt Bilirubin", "Direct Bilirubin", "Konjuge Bilirubin")),
    Phase1Definition(GROUP_LIVER, "ALB", "Albumin", ("Albumin", "Albümin")),
)


class Phase1ParameterSelector:
    """Decides Phase 1 activation for a given parameter name."""

    def __init__(self, definitions: tuple[Phase1Definition, ...] = _DEFINITIONS) -> None:
        self._definitions = definitions
        self._index: dict[str, Phase1Definition] = {}
        self._by_code: dict[str, Phase1Definition] = {}
        for definition in definitions:
            self._by_code[definition.code] = definition
            for alias in definition.aliases:
                key = normalize_alias(alias)
                if not key:
                    continue
                existing = self._index.get(key)
                if existing is not None and existing.code != definition.code:
                    raise ValueError(
                        f"Ambiguous Phase 1 alias {alias!r} maps to both "
                        f"{existing.code} and {definition.code}"
                    )
                self._index[key] = definition

    def match(self, parameter_name: str, category: str | None = None) -> Phase1Match | None:
        """Return a `Phase1Match` if `parameter_name` is a Phase 1 parameter.

        `category` is accepted for interface completeness but intentionally not
        used to activate: the CSV categories (e.g. Biyokimya, Hormon, CBC) do
        not map one-to-one onto Phase 1 groups, so the curated alias table is
        authoritative.
        """
        for key in self._candidate_keys(parameter_name):
            definition = self._index.get(key)
            if definition is not None:
                return Phase1Match(
                    group=definition.group,
                    code=definition.code,
                    canonical_name=definition.canonical_name,
                    aliases=definition.aliases,
                )
        return None

    def is_active(self, parameter_name: str, category: str | None = None) -> bool:
        return self.match(parameter_name, category) is not None

    def aliases_for(self, code: str) -> tuple[str, ...]:
        definition = self._by_code.get(code)
        return definition.aliases if definition else ()

    def iter_definitions(self):
        return iter(self._definitions)

    @staticmethod
    def _candidate_keys(parameter_name: str) -> tuple[str, ...]:
        primary = normalize_alias(parameter_name)
        without_parens = normalize_alias(strip_parenthetical(parameter_name))
        if without_parens and without_parens != primary:
            return (primary, without_parens)
        return (primary,)


# Module-level singleton for dependency injection / import-time reuse.
phase1_selector = Phase1ParameterSelector()
