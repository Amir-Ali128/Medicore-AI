from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


AUTH_SECRET_KEY = os.getenv(
    "AUTH_SECRET_KEY",
    "dev-medicore-change-this-secret-key",
)

TOKEN_TTL_SECONDS = 60 * 60 * 12
PASSWORD_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()

    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = hashed_password.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations_text),
    ).hex()

    return hmac.compare_digest(digest, expected_digest)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(payload: dict[str, Any]) -> str:
    token_payload = {
        **payload,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }

    payload_bytes = json.dumps(
        token_payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    payload_part = _b64encode(payload_bytes)

    signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    signature_part = _b64encode(signature)

    return f"{payload_part}.{signature_part}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload_part, signature_part = token.split(".")
    except ValueError:
        return None

    expected_signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    given_signature = _b64decode(signature_part)

    if not hmac.compare_digest(expected_signature, given_signature):
        return None

    try:
        payload = json.loads(_b64decode(payload_part))
    except json.JSONDecodeError:
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None

    return payload