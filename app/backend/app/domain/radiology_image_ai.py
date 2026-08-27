"""Experimental multimodal image review for X-ray and ultrasound screenshots.

This module deliberately produces assistive visual observations rather than a
radiologic diagnosis. It uses the already configured Anthropic account and keeps
the result explicitly marked for physician review.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class RadiologyImageReview:
    summary: str
    observations: list[str]
    limitations: list[str]
    visible_text: str
    model: str
    detected_modality: str


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


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline >= 0:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Görüntü modeli yapılandırılmış JSON döndürmedi.")
        value = json.loads(cleaned[start : end + 1])

    if not isinstance(value, dict):
        raise ValueError("Görüntü modeli beklenen nesne biçimini döndürmedi.")
    return value


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
) -> RadiologyImageReview | None:
    """Return an assistive visual review, or ``None`` when AI is not configured."""
    normalized_media_type = media_type.lower().strip()
    normalized_modality = normalize_image_modality(modality)
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

    prompt = f"""
{modality_context} Görüntü bir PACS ekran görüntüsü, cihaz ekranı veya rapor ekran
görüntüsü olabilir.

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

Yalnızca aşağıdaki JSON biçimini döndür:
{{
  "detected_modality": "XRAY | ULTRASOUND | UNKNOWN",
  "summary": "1-3 cümlelik tanısal olmayan genel özet",
  "observations": ["en fazla 6 doğrudan görsel gözlem"],
  "limitations": ["en fazla 5 sınırlama"],
  "visible_text": "varsa kimlik bilgileri çıkarılmış okunabilir rapor metni, yoksa boş"
}}
""".strip()

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=1100,
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

    if not summary:
        summary = "Görüntü için tanısal olmayan AI ön incelemesi oluşturuldu; hekim doğrulaması gereklidir."

    return RadiologyImageReview(
        summary=summary[:1800],
        observations=observations,
        limitations=limitations,
        visible_text=visible_text[:5000],
        model=model,
        detected_modality=detected_modality,
    )