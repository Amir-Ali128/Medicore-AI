"""Alias normalization.

Canonical lab-name normalization is owned by the native C++ deterministic core when
that extension is installed. The dependency-free Python implementation remains as a
rolling-deploy/dev fallback and is intentionally behavior-compatible for Turkish and
common Latin text.
"""

from __future__ import annotations

import re
import unicodedata

_TURKISH_FOLD = str.maketrans(
    {
        "ı": "i", "İ": "i",
        "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g",
        "ç": "c", "Ç": "c",
        "ö": "o", "Ö": "o",
        "ü": "u", "Ü": "u",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")


def _python_normalize_alias(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().translate(_TURKISH_FOLD).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _NON_ALNUM.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def normalize_alias(value: str | None) -> str:
    """Return the canonical lookup key, preferring the C++ implementation."""
    try:
        from app.domain.native_lab_engine import (
            native_lab_deterministic_available,
            native_normalize_alias,
        )

        if native_lab_deterministic_available():
            return native_normalize_alias(value)
    except (ImportError, RuntimeError, OSError):
        pass
    return _python_normalize_alias(value)


def normalization_tokens(value: str | None) -> list[str]:
    normalized = normalize_alias(value)
    return normalized.split(" ") if normalized else []


def strip_parenthetical(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\(.*?\)", " ", value).strip()
