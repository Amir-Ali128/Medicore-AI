"""Conservative report labels derived from existing report content.

This helper has no database or provider dependencies. Source text is only read;
recommendations, comparison studies and isolated modality mentions do not prove
the type of the current report.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

INFERENCE_VERSION = "report-type-v1"
REPORT_TYPES = frozenset(
    {"CT", "ULTRASOUND", "MRI", "X_RAY", "PATHOLOGY", "ECHOCARDIOGRAPHY", "ENDOSCOPY", "OTHER", "UNKNOWN"}
)

_PATTERNS = {
    "CT": r"\b(?:bt|ct|bilgisayarli\s+tomografi\w*|computed\s+tomography|tomografi\w*)\b",
    "ULTRASOUND": r"\b(?:usg|ultrasound|ultrason\w*|sonografi\w*|sonography|sonographic)\b",
    "MRI": r"\b(?:mr|mrg|mri|manyetik\s+rezonans\w*|magnetic\s+resonance)\b",
    "X_RAY": r"\b(?:x[ -]?ray|rontgen\w*|grafi\w*|radiograph\w*)\b",
    "PATHOLOGY": r"\b(?:patoloji(?:si|k\s+tani)?|pathology|histopatolo\w*|histopatholo\w*|sitopatolo\w*|cytopatholo\w*)\b",
    "ECHOCARDIOGRAPHY": r"\b(?:ekokardiyografi\w*|echocardiogra\w*|eko|echocardiogram)\b",
    "ENDOSCOPY": r"\b(?:endoskopi\w*|endoscopy|gastroskopi\w*|gastroscopy|kolonoskopi\w*|colonoscopy|bronkoskopi\w*|bronchoscopy)\b",
    "OTHER": r"\b(?:dexa|dxa|pet[ /-]?(?:ct|bt)|spect|sintigrafi\w*|electrocardiogram|elektrokardiyografi\w*)\b",
}
_COMPILED_PATTERNS = {code: re.compile(pattern) for code, pattern in _PATTERNS.items()}
_NON_CURRENT = re.compile(
    r"\b(?:oner\w*|recommend\w*|suggest\w*|consider\w*|planlan\w*|planned|"
    r"follow[ -]?up|takip\w*|kontrol\s+(?:amac\w*|icin)|previous\w*|prior|"
    r"onceki|gecmis|karsilastir\w*|compar\w*|history\s+of|oyku\w*|"
    r"yapilmadi|yapilmamis\w*|not\s+performed|isten\w*|requested|gerekirse|"
    r"gerekl\w*|may\s+be|should|could|alinmasi|cekilmesi)\b"
)
_CURRENT_PROCEDURE = re.compile(
    r"\b(?:inceleme\w*|tetkik\w*|examin\w*|study|studies|scan\w*|"
    r"goruntule\w*|imaging|rapor\w*|report\w*|teknik|technique|"
    r"shows?|demonstrat\w*|performed|elde\s+edil\w*|degerlendir\w*|"
    r"izlen\w*|saptan\w*|sonographic)\b"
)
_SECTION = re.compile(
    r"^(?:baslik|title|inceleme(?:\s+adi)?|examination|exam|tetkik|teknik|technique)\s*[:=-]"
)
_BODY_SECTION = re.compile(
    r"^(?:bulgular|findings|sonuc|impression|degerlendirme|klinik\s+bilgi|endikasyon|indication)\s*[:=-]?\s*"
)


@dataclass(frozen=True)
class ReportTypeInference:
    report_type: str
    confidence: float
    reasons: tuple[str, ...] = ()

    def to_metadata(self) -> dict[str, Any]:
        return {
            "inferred_report_type": self.report_type,
            "report_type_confidence": self.confidence,
            "report_type_inference": {"version": INFERENCE_VERSION, "reasons": list(self.reasons)},
        }


def _fold(value: str) -> str:
    translated = value.translate(str.maketrans("ıİşŞğĞüÜöÖçÇ", "iissgguuoocc"))
    normalized = unicodedata.normalize("NFKD", translated)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return "\n".join(_text(value[key]) for key in ("text", "finding", "findings") if key in value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return "\n".join(filter(None, (_text(item) for item in value)))
    if isinstance(getattr(value, "text", None), str):
        return value.text
    return ""


def _types(fragment: str) -> set[str]:
    codes = {code for code, pattern in _COMPILED_PATTERNS.items() if pattern.search(fragment)}
    # PET/CT and DXA are distinct examinations; their CT/X-ray components do
    # not make them standalone CT or plain radiograph reports.
    if "OTHER" in codes and re.search(r"\b(?:pet[ /-]?(?:ct|bt)|dexa|dxa)\b", fragment):
        codes.discard("CT")
        codes.discard("X_RAY")
    # Echocardiography is more specific than its ultrasound technique.
    if "ECHOCARDIOGRAPHY" in codes:
        codes.discard("ULTRASOUND")
    return codes


def infer_report_type(
    *,
    title: Any = None,
    examination: Any = None,
    technique: Any = None,
    findings: Any = None,
    impression: Any = None,
    source_text: Any = None,
    modality: str | None = None,
) -> ReportTypeInference:
    """Classify the current examination, or return UNKNOWN if evidence is weak.

    Titles and explicit examination/technique fields are stronger than body
    mentions. A stored modality alone is not trusted: older parsers may have
    inferred it from a recommendation for a different examination.
    """
    evidence: dict[str, tuple[float, set[str]]] = {}
    ignored_reference = False

    def add(code: str, score: float, reason: str) -> None:
        previous_score, previous_reasons = evidence.get(code, (0.0, set()))
        evidence[code] = (max(score, previous_score), previous_reasons | {reason})

    for name, raw in (
        ("title", title), ("examination", examination), ("technique", technique),
        ("findings", findings), ("impression", impression), ("source_text", source_text),
    ):
        fragments = re.split(r"\r?\n+|(?<=[.!?;])\s+", _text(raw))
        body_started = False
        nonempty_index = 0
        for fragment in fragments:
            folded = _fold(fragment).strip()
            if not folded:
                continue
            nonempty_index += 1
            if _BODY_SECTION.match(folded):
                body_started = True
            matches = _types(folded)
            if matches and _NON_CURRENT.search(folded):
                ignored_reference = True
                continue
            if name in {"title", "examination"}:
                score = 0.97
            elif name == "technique" or _SECTION.match(folded):
                score = 0.93
            elif (
                name == "source_text" and nonempty_index <= 4 and not body_started
                and len(folded) <= 140 and len(folded.split()) <= 12
                and not re.search(r"[.!?]$", folded)
            ):
                score = 0.94
            elif _CURRENT_PROCEDURE.search(folded):
                score = 0.86
            else:
                score = 0.35
            for code in matches:
                if code == "PATHOLOGY":
                    # "Pathology" in a CT/MRI finding means an abnormality;
                    # it does not identify a pathology department's report.
                    pathology_report = (
                        name in {"title", "examination"}
                        or re.search(
                            r"\b(?:histopatolo\w*|histopatholo\w*|sitopatolo\w*|cytopatholo\w*|"
                            r"patoloji\s+(?:rapor\w*|sonuc\w*|inceleme\w*)|"
                            r"pathology\s+(?:report|examination)|patolojik\s+tani)\b", folded
                        )
                        or re.fullmatch(r"(?:anatomi\s+)?patoloji|pathology", folded.strip(" :.-"))
                    )
                    pathology_absent = re.search(
                        r"\b(?:no\s+pathology|patoloji\w*\s+(?:yok\w*|saptanma\w*|izlenme\w*))\b",
                        folded,
                    )
                    if not pathology_report or pathology_absent:
                        continue
                add(code, score, f"{name}:explicit_{code.lower()}")
            # MRI pulse sequences can identify an otherwise unnamed technique.
            if name in {"technique", "source_text"} and not _NON_CURRENT.search(folded):
                if re.search(r"\bt1\w*\b", folded) and re.search(r"\bt2\w*\b", folded) and re.search(r"\b(?:sekans\w*|sequence\w*|flair|agirlikli|weighted)\b", folded):
                    add("MRI", 0.86, f"{name}:mri_sequences")

    declared = {"XRAY": "X_RAY", "X-RAY": "X_RAY", "USG": "ULTRASOUND", "BT": "CT", "MR": "MRI"}.get(
        (modality or "").upper(), (modality or "").upper()
    )
    if declared in REPORT_TYPES - {"UNKNOWN"}:
        add(declared, 0.35, "modality:unverified_existing_code")
    decisive = {code: item for code, item in evidence.items() if item[0] >= 0.8}
    if not decisive:
        reason = "references_only" if ignored_reference and not evidence else "insufficient_current_examination_evidence"
        return ReportTypeInference("UNKNOWN", 0.0, (reason,))
    # Multiple asserted examination types are ambiguous. Do not choose the
    # first regex match or let source order decide a clinical label.
    if len(decisive) != 1:
        return ReportTypeInference("UNKNOWN", 0.0, ("conflicting_examination_types",))
    code, (score, reasons) = next(iter(decisive.items()))
    return ReportTypeInference(code, score, tuple(sorted(reasons)))


def infer_existing_report_type(report: Any) -> ReportTypeInference:
    """Use the same inference for ORM reports, response schemas and legacy JSON."""
    def get(key: str, default: Any = None) -> Any:
        if isinstance(report, Mapping):
            return report.get(key, default)
        return getattr(report, key, default)

    metadata = get("metadata_json", {}) or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    return infer_report_type(
        title=metadata.get("title") or metadata.get("report_title"),
        examination=metadata.get("examination") or metadata.get("examination_name"),
        technique=metadata.get("technique"),
        findings=get("findings", get("findings_json")),
        impression=get("impression"),
        source_text=get("original_text", get("raw_text")),
        modality=get("modality") or metadata.get("report_type"),
    )
