from app.api.routes.radiology_image_review import _resolve_media_type
from app.domain.radiology_image_ai import SUPPORTED_MODALITIES, normalize_image_modality


def test_jpg_extension_resolves_to_jpeg_when_mime_is_missing() -> None:
    assert _resolve_media_type("chest-xray.jpg", None) == "image/jpeg"


def test_jpeg_extension_overrides_unknown_browser_mime() -> None:
    assert _resolve_media_type("ultrasound.jpeg", "application/octet-stream") == "image/jpeg"


def test_auto_modality_is_supported_and_normalized() -> None:
    assert normalize_image_modality("auto-detect") == "AUTO"
    assert "AUTO" in SUPPORTED_MODALITIES
