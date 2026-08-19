"""Public, non-PII protocol number generation for MediCore patients."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import secrets

# Excludes visually ambiguous characters such as 0/O and 1/I.
PROTOCOL_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
PROTOCOL_TOKEN_LENGTH = 10
PROTOCOL_PATTERN = re.compile(
    rf"^MDC-\d{{4}}-[{PROTOCOL_ALPHABET}]{{{PROTOCOL_TOKEN_LENGTH}}}$"
)


def normalize_protocol_no(value: str) -> str:
    """Normalize user-facing protocol numbers before display/comparison."""
    return value.strip().upper()


def generate_protocol_no(*, year: int | None = None) -> str:
    """Generate a non-sequential protocol number safe to expose in the UI.

    The protocol number is an identifier, not an authentication secret.
    """
    resolved_year = year or datetime.now(timezone.utc).year
    token = "".join(
        secrets.choice(PROTOCOL_ALPHABET)
        for _ in range(PROTOCOL_TOKEN_LENGTH)
    )
    return f"MDC-{resolved_year}-{token}"


def is_valid_protocol_no(value: str) -> bool:
    """Return whether a value matches the MediCore protocol format."""
    return bool(PROTOCOL_PATTERN.fullmatch(normalize_protocol_no(value)))
