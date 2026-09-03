from app.api.routes.radiology_image_review import _resolve_media_type
from app.domain.radiology_image_ai import SUPPORTED_MODALITIES, normalize_image_modality
from app.domain.report_document_image_ai import (
    _medical_image_guidance,
    _prefer_clinical_visual_summary,
    _separate_visual_observations,
)


def test_jpg_extension_resolves_to_jpeg_when_mime_is_missing() -> None:
    assert _resolve_media_type("chest-xray.jpg", None) == "image/jpeg"


def test_jpeg_extension_overrides_unknown_browser_mime() -> None:
    assert _resolve_media_type("ultrasound.jpeg", "application/octet-stream") == "image/jpeg"


def test_auto_modality_is_supported_and_normalized() -> None:
    assert normalize_image_modality("auto-detect") == "AUTO"
    assert "AUTO" in SUPPORTED_MODALITIES


def test_abdominal_xray_guidance_requests_clinically_useful_observations() -> None:
    guidance = _medical_image_guidance("XRAY", "ABDOMEN").lower()

    assert "gaz paterni" in guidance
    assert "dışkı/fekal yük" in guidance
    assert "hava-sıvı" in guidance
    assert "serbest subdiyafragmatik hava" in guidance
    assert "barsak" in guidance and "dilatasyonu" in guidance
    assert "omurga hizalanması" in guidance
    assert "kesin tanı" in guidance


def test_screenshot_quality_descriptions_are_moved_to_limitations() -> None:
    observations, limitations = _separate_visual_observations(
        [
            "Kolon boyunca gaz ve dışkı yükü izleniyor.",
            "Görüntü PACS ekran fotoğrafı ve moiré içeriyor.",
            "Belirgin yaygın barsak dilatasyonu seçilmiyor.",
        ],
        ["Tek projeksiyon değerlendirmeyi sınırlar."],
    )

    assert observations == [
        "Kolon boyunca gaz ve dışkı yükü izleniyor.",
        "Belirgin yaygın barsak dilatasyonu seçilmiyor.",
    ]
    assert any("PACS" in item for item in limitations)
    assert any("Tek projeksiyon" in item for item in limitations)


def test_low_value_pacs_summary_is_replaced_by_clinical_observations() -> None:
    summary = _prefer_clinical_visual_summary(
        "Bir bilgisayar ekranında PACS ekran fotoğrafı görülüyor; moiré artefaktı mevcut.",
        [
            "Sol üst kadranda belirgin gaz görünümü izleniyor.",
            "Belirgin yaygın barsak dilatasyonu seçilmiyor.",
        ],
    )

    assert "PACS" not in summary
    assert "gaz görünümü" in summary
    assert "barsak dilatasyonu" in summary
