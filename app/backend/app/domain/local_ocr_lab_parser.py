"""Local OCR fallback for image-only laboratory PDFs.

The existing native PDF parser remains the first choice. This module is used
only when a PDF has no usable text/table layer. It renders pages locally,
runs RapidOCR, corrects page orientation, reconstructs four-column laboratory
rows, and returns source-faithful values without clinical interpretation.

No patient document is sent to an external AI provider in this stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
import re
from typing import Any

# Keep native OCR libraries from spawning large thread pools on small Render instances.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np

_MIN_ACCEPTED_ROWS = 3
_HEADER_HINTS = ("TETKIK", "TAHLIL", "SONUC", "BIRIM", "REFERANS")
_VALUE_RE = re.compile(r"^\s*([<>]=?)?\s*(-?\d+(?:[.,]\d+)?)\s*$")
_RANGE_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*[-–—]\s*(-?\d+(?:[.,]\d+)?)\s*$")
_ONE_SIDED_RE = re.compile(r"^\s*([<>]=?)\s*(-?\d+(?:[.,]\d+)?)\s*$")


@dataclass(frozen=True)
class OcrToken:
    text: str
    score: float
    x: float
    y: float
    width: float
    height: float


def _fold(value: str) -> str:
    table = str.maketrans(
        {
            "İ": "I",
            "ı": "I",
            "Ş": "S",
            "ş": "S",
            "Ğ": "G",
            "ğ": "G",
            "Ü": "U",
            "ü": "U",
            "Ö": "O",
            "ö": "O",
            "Ç": "C",
            "ç": "C",
        }
    )
    return re.sub(r"\s+", " ", str(value).translate(table).upper()).strip()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _numeric_value(text: str) -> float | None:
    match = _VALUE_RE.fullmatch(_clean(text))
    if not match:
        return None
    try:
        return float(match.group(2).replace(",", "."))
    except ValueError:
        return None


def _reference_bounds(text: str) -> tuple[float | None, float | None]:
    cleaned = _clean(text)
    match = _RANGE_RE.fullmatch(cleaned)
    if match:
        return (
            float(match.group(1).replace(",", ".")),
            float(match.group(2).replace(",", ".")),
        )
    match = _ONE_SIDED_RE.fullmatch(cleaned)
    if match:
        number = float(match.group(2).replace(",", "."))
        return (None, number) if match.group(1).startswith("<") else (number, None)
    return None, None


def _tokens_from_result(result: Any) -> list[OcrToken]:
    if not result:
        return []

    rows = result[0] if isinstance(result, tuple) else result
    if not isinstance(rows, list):
        return []

    tokens: list[OcrToken] = []
    for item in rows:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        box, text, score = item[0], _clean(item[1]), item[2]
        if not text or not isinstance(box, (list, tuple)) or len(box) < 4:
            continue
        try:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            confidence = float(score)
        except (TypeError, ValueError, IndexError):
            continue
        tokens.append(
            OcrToken(
                text=text,
                score=confidence,
                x=(min(xs) + max(xs)) / 2,
                y=(min(ys) + max(ys)) / 2,
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
            )
        )
    return tokens


def _orientation_score(tokens: list[OcrToken]) -> float:
    if not tokens:
        return -1.0
    folded = " ".join(_fold(token.text) for token in tokens)
    header_hits = sum(hint in folded for hint in _HEADER_HINTS)
    confidence = sum(token.score for token in tokens) / max(len(tokens), 1)
    numeric_hits = sum(_numeric_value(token.text) is not None for token in tokens)
    return header_hits * 20 + min(numeric_hits, 20) + confidence * 10


@lru_cache(maxsize=1)
def _ocr_engine():
    try:
        import cv2
        cv2.setNumThreads(1)
    except Exception:
        pass

    from rapidocr_onnxruntime import RapidOCR

    # Model initialization is expensive; keep a single process-local instance.
    return RapidOCR()


def _ocr_once(image: np.ndarray) -> list[OcrToken]:
    try:
        result = _ocr_engine()(image)
    except Exception:
        return []
    return _tokens_from_result(result)


def _ocr_best_orientation(image: np.ndarray) -> list[OcrToken]:
    """OCR the minimum number of orientations needed for a table.

    The first successful orientation that exposes all four expected table
    columns wins. This avoids running four full ONNX passes for every page.
    """

    best_tokens: list[OcrToken] = []
    best_score = -1.0

    # Most PDFs are upright. The common scanned-photo case is ±90 degrees.
    # Try 180 only as a last resort.
    for turns in (0, 1, 3, 2):
        candidate = image if turns == 0 else np.ascontiguousarray(np.rot90(image, turns))
        tokens = _ocr_once(candidate)
        if not tokens:
            continue

        score = _orientation_score(tokens)
        if score > best_score:
            best_tokens = tokens
            best_score = score

        if _header_columns(tokens) is not None:
            return tokens

    return best_tokens


def _cluster_rows(tokens: list[OcrToken]) -> list[list[OcrToken]]:
    if not tokens:
        return []

    ordered = sorted(tokens, key=lambda token: (token.y, token.x))
    median_height = float(np.median([max(token.height, 1.0) for token in ordered]))
    tolerance = max(8.0, median_height * 0.65)

    rows: list[list[OcrToken]] = []
    centers: list[float] = []
    for token in ordered:
        best_index = None
        best_distance = None
        for index, center in enumerate(centers):
            distance = abs(token.y - center)
            if distance <= tolerance and (best_distance is None or distance < best_distance):
                best_index = index
                best_distance = distance
        if best_index is None:
            rows.append([token])
            centers.append(token.y)
        else:
            rows[best_index].append(token)
            centers[best_index] = sum(item.y for item in rows[best_index]) / len(rows[best_index])

    for row in rows:
        row.sort(key=lambda token: token.x)
    return rows


def _header_columns(tokens: list[OcrToken]) -> tuple[float, float, float, float] | None:
    folded_tokens = [(_fold(token.text), token) for token in tokens]

    def first_x(*needles: str) -> float | None:
        matches = [
            token.x
            for folded, token in folded_tokens
            if any(needle in folded for needle in needles)
        ]
        return min(matches) if matches else None

    test_x = first_x("TETKIK", "TAHLIL")
    result_x = first_x("SONUC")
    unit_x = first_x("BIRIM")
    reference_x = first_x("REFERANS")

    values = (test_x, result_x, unit_x, reference_x)
    if any(value is None for value in values):
        return None
    typed = tuple(float(value) for value in values if value is not None)
    if list(typed) != sorted(typed):
        return None
    return typed  # type: ignore[return-value]


def _assign_columns(
    row: list[OcrToken],
    columns: tuple[float, float, float, float],
) -> tuple[str, str, str, str]:
    test_x, result_x, unit_x, reference_x = columns
    boundaries = (
        (test_x + result_x) / 2,
        (result_x + unit_x) / 2,
        (unit_x + reference_x) / 2,
    )
    cells: list[list[str]] = [[], [], [], []]
    for token in row:
        if token.x < boundaries[0]:
            index = 0
        elif token.x < boundaries[1]:
            index = 1
        elif token.x < boundaries[2]:
            index = 2
        else:
            index = 3
        cells[index].append(token.text)
    return tuple(_clean(" ".join(cell)) for cell in cells)  # type: ignore[return-value]


def parse_ocr_tokens_to_lab_rows(
    tokens: list[OcrToken],
    *,
    page_number: int,
    file_name: str,
) -> list[dict[str, Any]]:
    """Reconstruct lab rows from OCR boxes. Kept separate for deterministic tests."""

    columns = _header_columns(tokens)
    if columns is None:
        return []

    rows: list[dict[str, Any]] = []
    for row in _cluster_rows(tokens):
        name, value_text, unit, reference = _assign_columns(row, columns)
        folded_name = _fold(name)

        if not name or not value_text:
            continue
        if any(header in folded_name for header in _HEADER_HINTS):
            continue
        if folded_name in {"TARIH", "TEST", "TESTLER"}:
            continue

        numeric = _numeric_value(value_text)
        # OCR fallback is intentionally conservative: require a numeric result
        # and a source reference before accepting a row as trustworthy enough
        # for automatic import.
        if numeric is None or not reference:
            continue

        reference_min, reference_max = _reference_bounds(reference)
        rows.append(
            {
                "raw_parameter_name": name,
                "raw_value": value_text,
                "normalized_value": numeric,
                "unit": None if unit in {"", "---", "—"} else unit,
                "reference_min": reference_min,
                "reference_max": reference_max,
                "reference_text": reference,
                "source_page": page_number,
                "source_file_name": file_name,
                "value_type": "numeric",
                "confidence": min(
                    0.94,
                    max(
                        0.70,
                        sum(token.score for token in row) / max(len(row), 1),
                    ),
                ),
                "needs_review": True,
            }
        )
    return rows


def try_local_ocr_lab_case(
    *,
    content: bytes,
    file_name: str,
) -> dict[str, Any] | None:
    """OCR an image-only PDF locally and return extracted lab rows when reliable."""

    if not content:
        return None

    try:
        import pymupdf
    except Exception:
        try:
            import fitz as pymupdf  # type: ignore[no-redef]
        except Exception:
            return None

    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception:
        return None

    all_rows: list[dict[str, Any]] = []
    try:
        for page_number, page in enumerate(document, start=1):
            # ~115 DPI is enough for printed lab tables while keeping CPU/RAM low.
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height,
                pixmap.width,
                pixmap.n,
            )
            if pixmap.n > 3:
                image = image[:, :, :3]

            tokens = _ocr_best_orientation(image)
            all_rows.extend(
                parse_ocr_tokens_to_lab_rows(
                    tokens,
                    page_number=page_number,
                    file_name=file_name,
                )
            )
    except Exception:
        return None
    finally:
        document.close()

    # Avoid silently importing garbage from arbitrary scanned documents.
    if len(all_rows) < _MIN_ACCEPTED_ROWS:
        return None

    return {
        "labs": all_rows,
        "warnings": [
            "local_ocr_lab_parser_v1",
            f"ocr_rows={len(all_rows)}",
            "ocr_rows_need_review",
        ],
        "extraction_confidence": min(
            row.get("confidence", 0.0) for row in all_rows
        ),
    }
