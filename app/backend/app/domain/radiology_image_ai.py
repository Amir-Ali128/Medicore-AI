"""Experimental multimodal image review for X-ray and ultrasound screenshots.

This module deliberately produces assistive visual observations rather than a
radiologic diagnosis. It uses the already configured Anthropic account and keeps
the result explicitly marked for physician review.
"""

from __future__ import annotations

import ast
import base64
import json
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import get_settings

SUPPORTED_IMAGE_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
SUPPORTED_MODALITIES = {"XRAY", "ULTRASOUND", "AUTO"}
_DETECTED_MODALITIES = {"XRAY", "ULTRASOUND", "UNKNOWN"}
_DETECTED_BODY_PARTS = {
    "ABDOMEN",
    "CHEST",
    "HEAD",
    "NECK",
    "PELVIS",
    "SPINE",
    "UPPER_EXTREMITY",
    "LOWER_EXTREMITY",
    "BREAST",
    "THYROID",
    "URINARY",
    "OBSTETRIC",
    "OTHER",
}


@dataclass(frozen=True)
class RadiologyImageReview:
    summary: str
    observations: list[str]
    limitations: list[str]
    visible_text: str
    model: str
    detected_modality: str
    detected_body_part: str


def normalize_image_modality(value: str | None) -> str | None:
    normalized = (value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "X_RAY": "XRAY",
        "X_RAY_IMAGE": "XRAY",
        "RADIOGRAPH": "XRAY",
        "RADIOGRAPHY": "XRAY",
        "RONTGEN": "XRAY",
        "RÖNTGEN": "XRAY",
        "US": "ULTRASOUND",
        "USG": "ULTRASOUND",
        "ULTRASON": "ULTRASOUND",
        "ULTRASONOGRAFI": "ULTRASOUND",
        "ULTRASONOGRAFİ": "ULTRASOUND",
        "AUTOMATIC": "AUTO",
        "AUTO_DETECT": "AUTO",
        "AUTODETECT": "AUTO",
    }
    return aliases.get(normalized, normalized or None)


def normalize_body_part(value: str | None) -> str | None:
    normalized = (value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "BATIN": "ABDOMEN",
        "KARIN": "ABDOMEN",
        "ABDOMINAL": "ABDOMEN",
        "THORAX": "CHEST",
        "TORAKS": "CHEST",
        "GOGUS": "CHEST",
        "GÖĞÜS": "CHEST",
        "BRAIN": "HEAD",
        "BEYIN": "HEAD",
        "BEYİN": "HEAD",
        "KAFA": "HEAD",
        "CERVICAL": "NECK",
        "BOYUN": "NECK",
        "OMURGA": "SPINE",
        "LOMBER": "SPINE",
        "LUMBAR": "SPINE",
        "PELVIC": "PELVIS",
        "UST_EKSTREMITE": "UPPER_EXTREMITY",
        "ÜST_EKSTREMİTE": "UPPER_EXTREMITY",
        "KOL": "UPPER_EXTREMITY",
        "EL": "UPPER_EXTREMITY",
        "ALT_EKSTREMITE": "LOWER_EXTREMITY",
        "ALT_EKSTREMİTE": "LOWER_EXTREMITY",
        "BACAK": "LOWER_EXTREMITY",
        "AYAK": "LOWER_EXTREMITY",
        "MEME": "BREAST",
        "TIROID": "THYROID",
        "TİROİD": "THYROID",
        "URINER": "URINARY",
        "ÜRİNER": "URINARY",
        "BOBREK": "URINARY",
        "BÖBREK": "URINARY",
        "GEBELIK": "OBSTETRIC",
        "GEBELİK": "OBSTETRIC",
        "OBSTETRIK": "OBSTETRIC",
        "OBSTETRİK": "OBSTETRIC",
    }
    candidate = aliases.get(normalized, normalized or None)
    return candidate if candidate in _DETECTED_BODY_PARTS else None


def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort structured parsing without failing the whole upload.

    Vision models occasionally wrap JSON in prose/code fences or return a
    Python-style dictionary. We recover those forms and, as a final fallback,
    keep the free-text answer as a non-diagnostic summary instead of raising a
    502 that would prevent the image from being saved.
    """
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
        "detected_modality": "UNKNOWN",
        "detected_body_part": "OTHER",
        "summary": compact[:1800]
        or "Görüntü modeli yapılandırılmış çıktı üretmedi; dosya hekim incelemesi için kaydedildi.",
        "observations": [],
        "limitations": [
            "Model yapılandırılmış JSON üretmedi; yalnızca serbest metin yanıtı güvenli özet olarak saklandı."
        ],
        "visible_text": "",
    }


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split()).strip()
        if cleaned:
            items.append(cleaned[:900])
        if len(items) >= limit:
            break
    return items


async def review_radiology_image(
    *,
    content: bytes,
    media_type: str,
    modality: str,
    body_part: str | None = None,
) -> RadiologyImageReview | None:
    """Return an assistive visual review, or ``None`` when AI is not configured."""
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

    if normalized_modality == "AUTO":
        modality_context = (
            "Görüntünün modalitesi kullanıcı tarafından belirtilmemiştir. Önce yalnızca "
            "görsel özelliklere göre bunun röntgen (XRAY), ultrason (ULTRASOUND) veya "
            "belirlenemeyen/uyumsuz (UNKNOWN) olduğunu sınıflandır."
        )
    else:
        modality_label = "röntgen" if normalized_modality == "XRAY" else "ultrason"
        modality_context = f"Bu görüntü kullanıcı tarafından {modality_label} olarak işaretlenmiştir."

    if requested_body_part:
        region_context = f"Kullanıcının belirttiği vücut bölgesi: {requested_body_part}."
    else:
        region_context = (
            "Vücut bölgesini yalnızca görüntüden güvenle ayırt edebiliyorsan sınıflandır; "
            "emin değilsen OTHER kullan."
        )

    prompt = f"""
{modality_context}
{region_context}
Görüntü bir PACS ekran görüntüsü, cihaz ekranı veya rapor ekran görüntüsü olabilir.

Amaç: hekime yardımcı olacak, TANISAL OLMAYAN bir ön inceleme üretmek.
- Kesin tanı koyma, hastalık olasılığı yüzdesi verme veya tedavi önerme.
- Yalnızca görüntüde doğrudan seçilebilen yapısal/görsel gözlemleri yaz.
- Görüntü kalitesi, kırpılma, tek projeksiyon, ekran fotoğrafı, artefakt gibi
  sınırlamaları açıkça belirt.
- Görüntüde rapor/metin varsa yalnızca okunabildiği kadarıyla visible_text alanına
  aktar; isim, T.C. kimlik no, telefon vb. kimlik bilgilerini yazma.
- Görüntü belirtilen modaliteyle uyumlu görünmüyorsa bunu sınırlama olarak belirt.
- Bulguları aşırı yorumlama; şüpheli görünen şeyi "hekim tarafından doğrulanmalı"
  şeklinde ifade et.
- detected_modality alanı yalnızca XRAY, ULTRASOUND veya UNKNOWN olmalıdır.
- detected_body_part alanı yalnızca ABDOMEN, CHEST, HEAD, NECK, PELVIS, SPINE,
  UPPER_EXTREMITY, LOWER_EXTREMITY, BREAST, THYROID, URINARY, OBSTETRIC veya OTHER olmalıdır.

Yalnızca aşağıdaki JSON biçimini döndür:
{{
  "detected_modality": "XRAY | ULTRASOUND | UNKNOWN",
  "detected_body_part": "ABDOMEN | CHEST | HEAD | NECK | PELVIS | SPINE | UPPER_EXTREMITY | LOWER_EXTREMITY | BREAST | THYROID | URINARY | OBSTETRIC | OTHER",
  "summary": "1-3 cümlelik tanısal olmayan genel özet",
  "observations": ["en fazla 6 doğrudan görsel gözlem"],
  "limitations": ["en fazla 5 sınırlama"],
  "visible_text": "varsa kimlik bilgileri çıkarılmış okunabilir rapor metni, yoksa boş"
}}
""".strip()

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=1200,
        system=(
            "You are a cautious medical imaging support component. Your output is "
            "assistive only, never a diagnosis, and always requires physician review."
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
    summary = " ".join(str(payload.get("summary") or "").split()).strip()
    observations = _string_list(payload.get("observations"), limit=6)
    limitations = _string_list(payload.get("limitations"), limit=5)
    visible_text = " ".join(str(payload.get("visible_text") or "").split()).strip()

    if normalized_modality in {"XRAY", "ULTRASOUND"}:
        detected_modality = normalized_modality
    else:
        detected_modality = (
            str(payload.get("detected_modality") or "UNKNOWN")
            .strip()
            .upper()
            .replace("-", "_")
            .replace(" ", "_")
        )
        if detected_modality not in _DETECTED_MODALITIES:
            detected_modality = "UNKNOWN"

    detected_body_part = requested_body_part or normalize_body_part(
        str(payload.get("detected_body_part") or "OTHER")
    ) or "OTHER"

    if not summary:
        summary = "Görüntü için tanısal olmayan AI ön incelemesi oluşturuldu; hekim doğrulaması gereklidir."

    return RadiologyImageReview(
        summary=summary[:1800],
        observations=observations,
        limitations=limitations,
        visible_text=visible_text[:5000],
        model=model,
        detected_modality=detected_modality,
        detected_body_part=detected_body_part,
    )
