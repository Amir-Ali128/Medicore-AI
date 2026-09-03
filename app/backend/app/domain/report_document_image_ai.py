"""Classify uploaded images as report documents or medical images.

Written report photos are extracted conservatively: direct identifiers are omitted,
explicit result/conclusion text is preserved separately, and other notable findings
are stored without inventing diagnoses. True medical images receive an assistive,
clinically useful visual review that remains non-diagnostic and physician-reviewable.
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

_MEDICAL_IMAGE_REGION_CHECKLISTS: dict[str, str] = {
    "ABDOMEN": (
        "Karın/batın görüntüsünde, görüntü gerçekten izin veriyorsa: mide gazı ve hava-sıvı "
        "seviyeleri; ince ve kalın bağırsak gaz paterni; dışkı/fekal yük; belirgin barsak "
        "dilatasyonu; diyaframlar görüntü alanındaysa serbest subdiyafragmatik hava; belirgin "
        "kalsifikasyon/yabancı cisim; kemik yapılar, omurga hizalanması ve hasta rotasyonu."
    ),
    "CHEST": (
        "Toraks görüntüsünde, görüntü gerçekten izin veriyorsa: akciğer alanlarında fokal/yaygın "
        "opasite; plevral sıvı veya pnömotoraks lehine bulgu; kardiyomediastinal silüet; "
        "diyafram ve kostofrenik sinüsler; belirgin kemik/cihaz bulguları ve rotasyon."
    ),
    "SPINE": (
        "Omurga görüntüsünde, görüntü gerçekten izin veriyorsa: koronal/sagittal hizalanma, "
        "vertebra yükseklikleri, belirgin eğrilik, akut kemik düzensizliği ve çekim/hasta "
        "rotasyonunun görünümü taklit edip edemeyeceği."
    ),
    "UPPER_EXTREMITY": (
        "Üst ekstremite görüntüsünde, görüntü gerçekten izin veriyorsa: kortikal süreklilik, "
        "eklem hizalanması, belirgin kırık/çıkık şüphesi, yumuşak doku şişliği ve yabancı cisim."
    ),
    "LOWER_EXTREMITY": (
        "Alt ekstremite görüntüsünde, görüntü gerçekten izin veriyorsa: kortikal süreklilik, "
        "eklem hizalanması, belirgin kırık/çıkık şüphesi, yumuşak doku şişliği ve yabancı cisim."
    ),
    "PELVIS": (
        "Pelvis görüntüsünde, görüntü gerçekten izin veriyorsa: pelvik halka ve kalça eklem "
        "hizalanması, belirgin kemik düzensizliği, kalça eklem aralıkları ve rotasyon."
    ),
    "HEAD": (
        "Baş görüntüsünde yalnızca modalitenin ve tek görüntünün güvenle gösterebildiği kemik, "
        "sinüs veya yumuşak doku özelliklerini değerlendir; görüntünün gösteremeyeceği intrakraniyal "
        "patolojileri dışlanmış gibi yazma."
    ),
    "NECK": (
        "Boyun görüntüsünde, görüntü gerçekten izin veriyorsa: servikal hizalanma, prevertebral "
        "yumuşak doku, belirgin kemik düzensizliği ve çekim rotasyonu."
    ),
    "URINARY": (
        "Üriner sistem görüntüsünde, modalite gerçekten izin veriyorsa: böbrek/mesane görünümü, "
        "dilatasyon, taş/kalsifik odak şüphesi, sıvı içerikli yapılar ve çevre dokular."
    ),
    "THYROID": (
        "Tiroid ultrasonunda, görüntü gerçekten izin veriyorsa: bez parankim görünümü, nodüler "
        "odaklar, kistik/solid özellikler ve ölçülebilir yapıların yalnızca görünen özellikleri."
    ),
    "BREAST": (
        "Meme görüntüsünde yalnızca doğrudan seçilebilen asimetri, kitle-benzeri odak, "
        "kalsifikasyon veya yapı bozukluğu gibi görsel özellikleri tarif et; BI-RADS veya kesin "
        "tanı üretme."
    ),
    "OBSTETRIC": (
        "Obstetrik görüntüde yalnızca açıkça görünen anatomik/ölçümsel özellikleri tarif et; "
        "tek kareden fetal sağlık, gebelik yaşı veya prognoz hakkında kesin sonuç üretme."
    ),
    "OTHER": (
        "Bölge belirsizse önce görüntüde güvenle seçilebilen anatomik bölgeyi ve modaliteye uygun "
        "ana yapıları değerlendir; görünmeyen yapılar hakkında negatif çıkarım yapma."
    ),
}

_VISUAL_LIMITATION_MARKERS = (
    "pacs",
    "ekran fotoğraf",
    "ekran fotograf",
    "bilgisayar ekran",
    "araç çubuğu",
    "arac cubugu",
    "moir",
    "yansıma",
    "yansima",
    "bulanık",
    "bulanik",
    "çözünürlük",
    "cozunurluk",
    "kırp",
    "kirp",
    "artefakt",
    "tek projeksiyon",
)


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


def _medical_image_guidance(modality: str | None, body_part: str | None) -> str:
    """Prompt guidance for clinically useful, non-diagnostic image observations."""

    region = body_part if body_part in _MEDICAL_IMAGE_REGION_CHECKLISTS else "OTHER"
    checklist = _MEDICAL_IMAGE_REGION_CHECKLISTS[region]
    modality_note = (
        "Röntgende yoğunluk, gaz paterni, hizalanma ve projeksiyonla değerlendirilebilen yapıları kullan."
        if modality == "XRAY"
        else (
            "Ultrasonda ekojenite, sıvı/solid görünüm, kontur ve yalnızca karede seçilebilen anatomiyi kullan."
            if modality == "ULTRASOUND"
            else "Modalitenin gerçekten gösterebildiği yapılarla sınırlı kal."
        )
    )

    return f"""
MEDICAL_IMAGE için çıktı, yalnızca görüntünün türünü tarif eden genel cümleler değil,
hekime gerçekten yararlı görsel gözlemler içermelidir.
- {modality_note}
- Bölgeye özgü kontrol listesi: {checklist}
- observations alanındaki her madde tek, klinik olarak anlamlı bir gözlem olsun.
- Önce pozitif/göze çarpan bulguları yaz. Ardından yalnızca görüntü alanı ve kalite gerçekten
  izin veriyorsa önemli negatif bulguları (ör. belirgin dilatasyon/serbest hava/kırık/efüzyon
  görülmemesi) yaz. Görüntünün göstermediği bir şeyi dışlanmış gibi yazma.
- PACS arayüzü, ekran fotoğrafı, moiré, yansıma, çözünürlük, kırpılma, tek projeksiyon,
  hasta rotasyonu gibi teknik noktalar observations yerine limitations alanına gitmelidir;
  rotasyon bir anatomik görünümü taklit edebiliyorsa ilgili observation içinde de bağlam olarak belirtilebilir.
- Görsel bulgunun düşük iddialı klinik anlamını belirtmek serbesttir: "... ile uyumlu olabilir",
  "... düşündürebilir" veya "tek başına anormal olmak zorunda değildir" gibi ifadeler kullanılabilir.
  Buna karşılık kesin tanı, olasılık yüzdesi, tedavi veya otomatik tetkik istemi üretme.
- summary 1-3 cümlelik klinik sentez olsun. "Bir görüntü/PACS ekranı görülüyor" gibi boş bir
  tanımla yetinme; en önemli 1-3 görsel bulguyu özetle ve gerekiyorsa önemli bir negatif bulguyu ekle.
- Emin olmadığın bir yapıyı adlandırma. Belirsizliği açıkça yaz ve hekim doğrulaması gerektiğini koru.
""".strip()


def _separate_visual_observations(
    observations: list[str], limitations: list[str]
) -> tuple[list[str], list[str]]:
    """Move low-value screenshot/quality descriptions out of clinical observations."""

    clinical: list[str] = []
    technical = list(limitations)
    for observation in observations:
        folded = observation.lower()
        if any(marker in folded for marker in _VISUAL_LIMITATION_MARKERS):
            if observation not in technical:
                technical.append(observation)
        elif observation not in clinical:
            clinical.append(observation)

    deduped_limitations: list[str] = []
    for limitation in technical:
        if limitation not in deduped_limitations:
            deduped_limitations.append(limitation)
    return clinical[:10], deduped_limitations[:8]


def _prefer_clinical_visual_summary(summary: str, observations: list[str]) -> str:
    """Replace a purely screenshot-descriptive summary when clinical observations exist."""

    if not observations:
        return summary
    folded = summary.lower()
    low_value_hits = sum(1 for marker in _VISUAL_LIMITATION_MARKERS if marker in folded)
    if not summary or low_value_hits >= 2:
        return " ".join(observations[:3])[:1800]
    return summary


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
    image_guidance = _medical_image_guidance(normalized_modality, requested_body_part)

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

{image_guidance}
Metin ağırlıklı rapor sayfasını MEDICAL_IMAGE sayma.

Yalnızca JSON döndür:
{{
  "document_kind":"REPORT_DOCUMENT | MEDICAL_IMAGE | OTHER",
  "detected_modality":"XRAY | ULTRASOUND | CT | MRI | MAMMOGRAPHY | DEXA | PET_CT | NUCLEAR_MEDICINE | ENDOSCOPY | PATHOLOGY | OTHER | UNKNOWN",
  "detected_body_part":"ABDOMEN | CHEST | HEAD | NECK | PELVIS | SPINE | UPPER_EXTREMITY | LOWER_EXTREMITY | BREAST | THYROID | URINARY | OBSTETRIC | OTHER",
  "report_type":"rapor türünün kısa adı veya UNKNOWN",
  "summary":"MEDICAL_IMAGE ise klinik olarak anlamlı 1-3 cümlelik görsel sentez; REPORT_DOCUMENT ise kısa kaynak özeti",
  "result_text":"açık sonuç/izlenim/kanaat bölümü veya boş",
  "result_items":["sonuç bölümündeki ayrı ifadeler"],
  "key_findings":["diğer bölümlerdeki önemli açık bulgular"],
  "recommendations":["açık öneriler"],
  "comparison_text":"varsa karşılaştırma, yoksa boş",
  "observations":["MEDICAL_IMAGE ise en fazla 10 klinik olarak anlamlı doğrudan görsel gözlem"],
  "limitations":["en fazla 8 teknik/kalite/sınırlandırıcı unsur"],
  "visible_text":"kimlik bilgileri çıkarılmış klinik metin"
}}
""".strip()

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=2800,
        temperature=0,
        system=(
            "You extract medical report documents conservatively and review medical images as a cautious "
            "radiology-assist component. For medical images, be clinically descriptive rather than merely "
            "describing the screenshot. Never invent findings, make a definitive diagnosis, prescribe treatment, "
            "or order tests. Remove direct identifiers. Return JSON only."
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
    observations = _string_list(payload.get("observations"), limit=10, item_limit=1000)
    limitations = _string_list(payload.get("limitations"), limit=8, item_limit=1000)
    visible_text = _clean(payload.get("visible_text"), 14000)
    summary = _clean(payload.get("summary"), 1800)

    if kind == "MEDICAL_IMAGE":
        observations, limitations = _separate_visual_observations(observations, limitations)
        summary = _prefer_clinical_visual_summary(summary, observations)
    elif kind == "REPORT_DOCUMENT" and not summary:
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
