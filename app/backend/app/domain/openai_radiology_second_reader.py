"""Independent OpenAI multimodal second reader for radiology uploads.

This adapter intentionally receives the original image rather than Claude output so
provider agreement is not manufactured by cross-contamination. It can also act as a
provider failover when Anthropic is unavailable. Output remains assistive,
non-diagnostic and physician-review-only.
"""

from __future__ import annotations

import base64

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.domain.radiology_image_ai import (
    SUPPORTED_IMAGE_MEDIA_TYPES,
    SUPPORTED_MODALITIES,
    normalize_body_part,
    normalize_image_modality,
)
from app.domain.report_document_image_ai import (
    RadiologyMediaReview,
    _clean,
    _detected_modality,
    _document_kind,
    _extract_json,
    _medical_image_guidance,
    _prefer_clinical_visual_summary,
    _separate_visual_observations,
    _string_list,
)


async def review_radiology_media_openai(
    *,
    content: bytes,
    media_type: str,
    modality: str,
    body_part: str | None = None,
) -> RadiologyMediaReview | None:
    """Review an uploaded radiology image independently with OpenAI vision.

    Returns ``None`` when the OpenAI second reader is disabled/not configured.
    The request is stateless (``store=False``) and never receives another model's
    interpretation.
    """

    normalized_media_type = media_type.lower().strip()
    normalized_modality = normalize_image_modality(modality)
    requested_body_part = normalize_body_part(body_part)
    if normalized_media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
        return None
    if normalized_modality not in SUPPORTED_MODALITIES:
        return None

    settings = get_settings()
    model = (settings.openai_vision_model or "").strip()
    if (
        not settings.openai_radiology_second_reader_enabled
        or not settings.openai_api_key
        or not model
    ):
        return None

    modality_context = (
        "Kullanıcı modalite belirtmedi; belge başlığı veya görüntü özelliklerinden sınıflandır."
        if normalized_modality == "AUTO"
        else f"Kullanıcı modaliteyi {normalized_modality} olarak işaretledi; belge fotoğrafıysa yine REPORT_DOCUMENT seç."
    )
    region_context = (
        f"Kullanıcının belirttiği bölge: {requested_body_part}."
        if requested_body_part
        else "Vücut bölgesini yalnızca açık görüntü/metin kanıtından çıkar; emin değilsen OTHER kullan."
    )
    image_guidance = _medical_image_guidance(normalized_modality, requested_body_part)

    prompt = f"""
Sen MediCore-AI içinde BAĞIMSIZ ikinci okuyucusun. Başka bir modelin yorumunu görmüyorsun;
yalnızca bu yüklenen görüntüyü değerlendiriyorsun. Çıktın hekim incelemesine yardımcı olur,
kesin tanı değildir ve kalibre edilmiş bir radyoloji anomaly-detector skoru gibi sunulmamalıdır.

{modality_context}
{region_context}

Önce içerik türünü ayır:
- REPORT_DOCUMENT: yazılı/taranmış/fotoğraflanmış tıbbi rapor sayfası.
- MEDICAL_IMAGE: röntgen, ultrason karesi, PACS/cihaz görüntüsü.
- OTHER: güvenle sınıflandırılamayan içerik.

GİZLİLİK: Ad-soyad, T.C. kimlik no, protokol no, telefon, adres, e-posta,
doğum tarihi gibi doğrudan tanımlayıcıları hiçbir çıktı alanına yazma.

REPORT_DOCUMENT ise:
- visible_text: yalnızca kimlik bilgileri çıkarılmış klinik rapor metni.
- result_text: yalnızca açık SONUÇ / İZLENİM / KANAAT / DEĞERLENDİRME /
  IMPRESSION / CONCLUSION / DIAGNOSIS bölümünün metni. Yoksa boş bırak.
- result_items: result_text içindeki ayrı sonuç ifadeleri.
- key_findings: raporun diğer bölümlerinde açıkça yazan önemli bulgular; yeni tanı üretme.
- recommendations: yalnızca raporda açıkça yazan takip/tetkik/öneri ifadeleri.
- comparison_text: yalnızca açık karşılaştırma bilgisi.

MEDICAL_IMAGE ise:
{image_guidance}
- Görüntüde seçilebilen olası anormal örüntüleri ve önemli değerlendirilebilir negatifleri yaz.
- Teknik ekran/PACS/moiré/kırpılma/tek projeksiyon gibi noktaları limitations alanına koy.
- Şüpheli bir görsel bulgunun düşük iddialı anlamını "... ile uyumlu olabilir" veya
  "... düşündürebilir" şeklinde yazabilirsin; kesin tanı, yüzde olasılık, tedavi veya otomatik
  tetkik istemi üretme.
- Görüntünün göstermediği veya kalitenin izin vermediği bir şeyi dışlanmış gibi yazma.
- Başka bir modelle anlaşma/uyuşmazlık hakkında yorum yapma; karşılaştırmayı MediCore yapacak.

Yalnızca şu JSON nesnesini döndür:
{{
  "document_kind":"REPORT_DOCUMENT | MEDICAL_IMAGE | OTHER",
  "detected_modality":"XRAY | ULTRASOUND | CT | MRI | MAMMOGRAPHY | DEXA | PET_CT | NUCLEAR_MEDICINE | ENDOSCOPY | PATHOLOGY | OTHER | UNKNOWN",
  "detected_body_part":"ABDOMEN | CHEST | HEAD | NECK | PELVIS | SPINE | UPPER_EXTREMITY | LOWER_EXTREMITY | BREAST | THYROID | URINARY | OBSTETRIC | OTHER",
  "report_type":"rapor türünün kısa adı veya UNKNOWN",
  "summary":"MEDICAL_IMAGE için en önemli görsel bulguların 1-3 cümlelik klinik sentezi; REPORT_DOCUMENT için kısa kaynak özeti",
  "result_text":"açık sonuç/izlenim/kanaat bölümü veya boş",
  "result_items":["sonuç bölümündeki ayrı ifadeler"],
  "key_findings":["rapordaki diğer açık önemli bulgular"],
  "recommendations":["yalnızca açık öneriler"],
  "comparison_text":"varsa karşılaştırma, yoksa boş",
  "observations":["MEDICAL_IMAGE ise en fazla 10 klinik olarak anlamlı doğrudan görsel gözlem"],
  "limitations":["en fazla 8 teknik/kalite/sınırlandırıcı unsur"],
  "visible_text":"kimlik bilgileri çıkarılmış klinik metin"
}}
""".strip()

    image_url = (
        f"data:{normalized_media_type};base64,"
        + base64.b64encode(content).decode("ascii")
    )
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(
        model=model,
        store=False,
        max_output_tokens=2800,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "high",
                    },
                ],
            }
        ],
    )

    text = _clean(getattr(response, "output_text", ""), 30000)
    if not text:
        raise ValueError("OpenAI görüntü modeli metin yanıtı döndürmedi.")

    payload = _extract_json(text)
    kind = _document_kind(payload.get("document_kind"))
    detected_modality = _detected_modality(payload.get("detected_modality"))
    if normalized_modality in {"XRAY", "ULTRASOUND"}:
        detected_modality = normalized_modality

    detected_body_part = requested_body_part or normalize_body_part(
        _clean(payload.get("detected_body_part"), 80)
    ) or "OTHER"
    result_text = _clean(payload.get("result_text"), 5000)
    result_items = tuple(
        _string_list(payload.get("result_items"), limit=24, item_limit=1200)
    )
    key_findings = tuple(
        _string_list(payload.get("key_findings"), limit=24, item_limit=1200)
    )
    recommendations = tuple(
        _string_list(payload.get("recommendations"), limit=12, item_limit=1200)
    )
    comparison_text = _clean(payload.get("comparison_text"), 2000)
    observations = _string_list(payload.get("observations"), limit=10, item_limit=1000)
    limitations = _string_list(payload.get("limitations"), limit=8, item_limit=1000)
    visible_text = _clean(payload.get("visible_text"), 14000)
    summary = _clean(payload.get("summary"), 1800)

    if kind == "MEDICAL_IMAGE":
        observations, limitations = _separate_visual_observations(
            observations,
            limitations,
        )
        summary = _prefer_clinical_visual_summary(summary, observations)
    elif kind == "REPORT_DOCUMENT" and not summary:
        summary = result_text or " ".join(result_items) or " ".join(key_findings)

    if not summary:
        summary = "OpenAI ikinci okuyucu incelemesi tamamlandı; hekim doğrulaması gereklidir."

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
