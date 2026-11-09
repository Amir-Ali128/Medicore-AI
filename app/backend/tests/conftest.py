"""Explicit synthetic OCR fixture for pre-existing mocked provider tests."""
import pytest

@pytest.fixture
def synthetic_privacy_ocr(monkeypatch):
    from app.domain import privacy_gateway
    from tests.test_privacy_gateway import fake_tokens
    def ocr(image, **kwargs):
        tokens=fake_tokens(image)
        return tokens[1:] if max(image.getpixel((200,50)))<10 else tokens
    monkeypatch.setattr(privacy_gateway,'_ocr_tokens',ocr)
