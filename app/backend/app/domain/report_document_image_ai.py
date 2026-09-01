"""Classify uploaded images as report documents or medical images.

Written report photos are extracted conservatively: direct identifiers are omitted,
explicit result/conclusion text is preserved separately, and other notable findings
are stored without inventing diagnoses. True medical images continue to receive a
non-diagnostic visual review.
"""

from __future__ import annotations

import ast
import base64
import json
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.domain.radiology_image_ai import (
    SUPPORTED_IMAGE_MEDIA_TYPES,
    SUPPORTED_MODALITIES,
    normalize_body_part,
    normalize_image_modality,
)

_DETECTED_MODALITIES = {
    "XRAY",
    "ULTRASOUND",
    "CT",
    "MRI",
    "MAMMOGRAPHY",
    "DEXA",
    "PET_CT",
    "NUCLEAR_MEDICINE",
    "ENDOSCOPY",
    "PATHOLOGY",
    "OTHER",
    "UNKNOWN",
}
_DOCUMENT_KINDS = {"REPORT_DOCUMENT", "MEDICAL_IMAGE", "OTHER"}


@dataclass(frozen=True)
class RadiologyMediaReview:
    summary: str
    observations: list[str]
    limitations: list[str]
    visible_text: str
    model: str
    detected_modality: str
    detected_body_part: str
    document_kind: str
    report_type: str
    result_text: str
    result_items: tuple[str, ...]
    key_findings: tuple[str, ...]
    recommendations: tuple[str, ...]
    comparison_text: str


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline >= 0:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        candidates.append(cleaned[start : end + 1])

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                value = ast.literal_eval(candidate)
            except (ValueError, SyntaxError):
                continue
        if isinstance(value, dict):
            return value

    compact = " ".join(cleaned.split()).strip()
    return {
        "document_kind": "OTHER",
        "detected_modality": "UNKNOWN",
        "detected_body_part": "OTHER",
        "report_type": "UNKNOWN",
        "summary": compact[:1800],
        "result_text": "",
        "result_items": [],
        "key_findings": [],
        "recommendations": [],
        "comparison_text": "",
        "observations": [],
        "limitations": ["Model yapılandırılmış JSON üretmedi; serbest metin yanıtı saklandı."],
        "visible_text": "",
    }


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _string_list(value: object, *, limit: int, item_limit: int = 1000) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = _clean(item, item_limit)
        if text and text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _document_kind(value: object) -> str:
    candidate = _clean(value, 40).upper().replace("-", "_").replace(" ", "_")
    return candidate if candidate in _DOCUMENT_KINDS else "OTHER"


def _detected_modality(value: object) -> str:
    candidate = _clean(value, 80).upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "US": "ULTRASOUND",
        "USG": "ULTRASOUND",
        "ULTRASON": "ULTRASOUND",
        "ULTRASONOGRAFI": "ULTRASOUND",
        "ULTRASONOGRAFİ": "ULTRASOUND",
        "BT": "CT",
        "MR": "MRI",
        "MRG": "MRI",
        "MAMOGRAFI": "MAMMOGRAPHY",
        "MAMMOGRAFİ": "MAMMOGRAPHY",
        "PETCT": "PET_CT",
    }
    candidate = aliases.get(candidate, candidate)
    return candidate if candidate in _DETECTED_MODALITIES else "UNKNOWN"


async def review_radiology_media(
    *,
    content: bytes,
    media_type: str,
    modality: str,
    body_part: str | None = None,
) -> RadiologyMediaReview | None:
    normalized_media_type = media_type.lower().strip()
    normalized_modality = normalize_image_modality(modality)
    requested_body_part = normalize_body_part(body_part)
    if normalized_media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
        return None
    if normalized_modality not in SUPPORTED_MODALITIES:
        return None

    settings = get_settings()
    model = (
        settings.claude_vision_model
        or settings.claude_hypothesis_model
        or settings.claude_extraction_model
    )
    if not settings.anthropic_api_key or not model:
        return None

    modality_context = (
        "Kullanıcı modalite belirtmedi; rapor başlığı veya görüntüden sınıflandır."
        if normalized_modality == "AUTO"
        else f"Kullanıcı modaliteyi {normalized_modality} olarak işaretledi; belge fotoğrafıysa yine REPORT_DOCUMENT seç."
    )
    region_context = (
        f"Kullanıcının belirttiği bölge: {requested_body_part}."
        if requested_body_part
        else "Bölgeyi yalnızca açık metin/görüntü kanıtından çıkar; emin değilsen OTHER kullan."
    )

    prompt = f"""
{modality_context}
{region_context}

Önce içerik türünü ayır:
- REPORT_DOCUMENT: yazılı/taranmış/fotoğraflanmış tıbbi rapor sayfası.
- MEDICAL_IMAGE: röntgen, ultrason karesi, PACS/cihaz görüntüsü.
- OTHER: güvenle sınıflandırılamayan içerik.

GİZLİLİK: Ad-soyad, T.C. kimlik no, protokol no, telefon, adres, e-posta,
doğum tarihi gibi doğrudan tanımlayıcıları hiçbir çıktı alanına yazma.

REPORT_DOCUMENT ise:
- detected_modality: XRAY, ULTRASOUND, CT, MRI, MAMMOGRAPHY, DEXA, PET_CT,
  NUCLEAR_MEDICINE, ENDOSCOPY, PATHOLOGY, OTHER veya UNKNOWN.
- visible_text: yalnızca kimlik bilgileri çıkarılmış klinik rapor metni.
- result_text: SADECE açık SONUÇ / İZLENİM / KANAAT / DEĞERLENDİRME /
  IMPRESSION / CONCLUSION / DIAGNOSIS bölümünün metni. Yoksa boş bırak.
- result_items: result_text içindeki ayrı sonuç ifadelerini maddelere ayır.
- key_findings: raporun diğer bölümlerindeki önemli açık bulgular. Ölçüm, organ
  büyüklüğü, kist/nodül/lezyon, dilatasyon, fibrozis evresi, kırık, efüzyon,
  stenoz gibi raporda açıkça yazan farklı bulguları kaçırma; yeni tanı üretme.
- recommendations: yalnızca açık ileri tetkik/takip/öneri ifadeleri.
- comparison_text: yalnızca açık KARŞILAŞTIRMA/önceki tetkik kıyaslaması.
- Tek sayfa 1/2 veya 2/2 olabilir; görünmeyen sayfanın içeriğini tahmin etme.

MEDICAL_IMAGE ise kesin tanı koyma. Yalnızca doğrudan görsel observations ve
limitations üret. Metin ağırlıklı rapor sayfasını MEDICAL_IMAGE sayma.

Yalnızca JSON döndür:
{{
  "document_kind":"REPORT_DOCUMENT | MEDICAL_IMAGE | OTHER",
  "detected_modality":"XRAY | ULTRASOUND | CT | MRI | MAMMOGRAPHY | DEXA | PET_CT | NUCLEAR_MEDICINE | ENDOSCOPY | PATHOLOGY | OTHER | UNKNOWN",
  "detected_body_part":"ABDOMEN | CHEST | HEAD | NECK | PELVIS | SPINE | UPPER_EXTREMITY | LOWER_EXTREMITY | BREAST | THYROID | URINARY | OBSTETRIC | OTHER",
  "report_type":"rapor türünün kısa adı veya UNKNOWN",
  "summary":"kısa ve sadece kaynağa dayalı özet",
  "result_text":"açık sonuç/izlenim/kanaat bölümü veya boş",
  "result_items":["sonuç bölümündeki ayrı ifadeler"],
  "key_findings":["diğer bölümlerdeki önemli açık bulgular"],
  "recommendations":["açık öneriler"],
  "comparison_text":"varsa karşılaştırma, yoksa boş",
  "observations":["MEDICAL_IMAGE ise en fazla 8 doğrudan gözlem"],
  "limitations":["en fazla 6 sınırlama"],
  "visible_text":"kimlik bilgileri çıkarılmış klinik metin"
}}
""".strip()

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=2400,
        temperature=0,
        system=(
            "You extract medical report documents conservatively and review medical images assistively. "
            "Never invent findings, diagnoses, or treatment. Remove direct identifiers. Return JSON only."
        ),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": normalized_media_type,
                            "data": base64.b64encode(content).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    text_parts = [
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    if not text_parts:
        raise ValueError("Görüntü modeli metin yanıtı döndürmedi.")

    payload = _extract_json("\n".join(text_parts))
    kind = _document_kind(payload.get("document_kind"))
    detected_modality = _detected_modality(payload.get("detected_modality"))
    if normalized_modality in {"XRAY", "ULTRASOUND"}:
        detected_modality = normalized_modality

    detected_body_part = requested_body_part or normalize_body_part(
        _clean(payload.get("detected_body_part"), 80)
    ) or "OTHER"
    result_text = _clean(payload.get("result_text"), 5000)
    result_items = tuple(_string_list(payload.get("result_items"), limit=24, item_limit=1200))
    key_findings = tuple(_string_list(payload.get("key_findings"), limit=24, item_limit=1200))
    recommendations = tuple(_string_list(payload.get("recommendations"), limit=12, item_limit=1200))
    comparison_text = _clean(payload.get("comparison_text"), 2000)
    observations = _string_list(payload.get("observations"), limit=8, item_limit=1000)
    limitations = _string_list(payload.get("limitations"), limit=6, item_limit=1000)
    visible_text = _clean(payload.get("visible_text"), 14000)
    summary = _clean(payload.get("summary"), 1800)

    if kind == "REPORT_DOCUMENT" and not summary:
        summary = result_text or " ".join(result_items) or " ".join(key_findings)
    if not summary:
        summary = "Dosya klinik inceleme için kaydedildi; hekim doğrulaması gereklidir."

    return RadiologyMediaReview(
        summary=summary[:1800],
        observations=observations,
        limitations=limitations,
        visible_text=visible_text,
        model=model,
        detected_modality=detected_modality,
        detected_body_part=detected_body_part,
        document_kind=kind,
        report_type=_clean(payload.get("report_type"), 140) or "UNKNOWN",
        result_text=result_text,
        result_items=result_items,
        key_findings=key_findings,
        recommendations=recommendations,
        comparison_text=comparison_text,
    )
