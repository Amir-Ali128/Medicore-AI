from types import SimpleNamespace

from app.api.routes.extraction import _resolve_content_type
from app.domain.claude_lab_extraction_service import (
    SUPPORTED_CONTENT_TYPES,
    ClaudeLabExtractionService,
)


def test_jpg_extension_resolves_to_image_jpeg_with_generic_mime() -> None:
    upload = SimpleNamespace(
        content_type="application/octet-stream",
        filename="hemogram.JPG",
    )

    assert _resolve_content_type(upload) == "image/jpeg"


def test_jpeg_is_supported_as_multimodal_lab_image() -> None:
    assert "image/jpeg" in SUPPORTED_CONTENT_TYPES

    block = ClaudeLabExtractionService._build_file_block("image/jpeg", "YWJj")

    assert block["type"] == "image"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "image/jpeg"
