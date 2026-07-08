"""Alias normalization.

Deterministic, dependency-free normalization used both when matching raw lab
test names against canonical parameters and when persisting `normalized_alias`
lookup keys. Turkish-aware: dotted/dotless i and the ç/ğ/ö/ş/ü letters are
folded to ASCII so that "İnsülin", "Insulin" and "insulin" collapse to one key.
"""

from __future__ import annotations

import re
import unicodedata

# Fold Turkish-specific letters to ASCII before generic diacritic stripping.
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


def normalize_alias(value: str | None) -> str:
    """Return a canonical lookup key for a lab test name or alias.

    Lowercased, Turkish/diacritic-folded, punctuation-collapsed to single
    spaces, and trimmed. Empty/None input yields an empty string.
    """
    if not value:
        return ""
    text = value.strip().translate(_TURKISH_FOLD).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _NON_ALNUM.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def normalization_tokens(value: str | None) -> list[str]:
    """Return the normalized whitespace-separated tokens of `value`."""
    normalized = normalize_alias(value)
    return normalized.split(" ") if normalized else []


def strip_parenthetical(value: str | None) -> str:
    """Return `value` with any `(...)` segments removed (pre-normalization)."""
    if not value:
        return ""
    return re.sub(r"\(.*?\)", " ", value).strip()
