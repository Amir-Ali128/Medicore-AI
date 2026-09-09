from __future__ import annotations

import io

from pypdf import PdfWriter

from app.api.routes.scanned_medical_report_pdf import _looks_like_pdf, _native_pdf_text


def test_pdf_detection_by_extension_or_content_type() -> None:
    assert _looks_like_pdf("report.pdf", "application/octet-stream") is True
    assert _looks_like_pdf("report.bin", "application/pdf") is True
    assert _looks_like_pdf("report.txt", "text/plain") is False


def test_image_only_pdf_has_no_embedded_text() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)

    assert _native_pdf_text(buffer.getvalue()) is None
