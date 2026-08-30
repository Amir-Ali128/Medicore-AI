"""Claude Sonnet 5 request compatibility and diagnostics.

Sonnet 5 rejects non-default sampling parameters such as ``temperature=0`` and
runs adaptive thinking by default. MediCore's compact clinical call needs a tiny,
deterministic JSON response, so this runtime shim removes legacy sampling knobs
and disables thinking for Sonnet 5 while preserving the existing 120-token cap.

The wrapper also logs a sanitized Anthropic error classification (status/type/
request id/model) before the existing clinical fallback handles the failure.
Secrets and prompt contents are never logged.
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from anthropic.resources.messages.messages import AsyncMessages
except ImportError:  # pragma: no cover - SDK layout compatibility
    from anthropic.resources.messages import AsyncMessages  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

_original_create = AsyncMessages.create


def _is_sonnet5(model: object) -> bool:
    return str(model or "").strip().lower().startswith("claude-sonnet-5")


def _compatible_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return request kwargs compatible with Sonnet 5 compact inference."""

    adjusted = dict(kwargs)
    if not _is_sonnet5(adjusted.get("model")):
        return adjusted

    # Sonnet 5 rejects non-default sampling values with HTTP 400. The compact
    # clinical service historically sent temperature=0, which is not accepted.
    adjusted.pop("temperature", None)
    adjusted.pop("top_p", None)
    adjusted.pop("top_k", None)

    # Adaptive thinking is enabled by default on Sonnet 5 and counts against
    # max_tokens. This call only needs a tiny JSON object, so explicitly disable
    # thinking to keep the existing 120-token budget meaningful and predictable.
    adjusted.setdefault("thinking", {"type": "disabled"})
    return adjusted


async def _create_with_sonnet5_compat(self: Any, *args: Any, **kwargs: Any) -> Any:
    adjusted = _compatible_kwargs(kwargs)
    model = adjusted.get("model")

    try:
        return await _original_create(self, *args, **adjusted)
    except Exception as exc:
        # Do not log prompts, API keys, response bodies, or other sensitive data.
        logger.exception(
            "Anthropic messages.create failed: model=%s error_type=%s status=%s request_id=%s",
            model,
            type(exc).__name__,
            getattr(exc, "status_code", None),
            getattr(exc, "request_id", None),
        )
        raise


if not getattr(AsyncMessages.create, "_medicore_sonnet5_compat", False):
    setattr(_create_with_sonnet5_compat, "_medicore_sonnet5_compat", True)
    AsyncMessages.create = _create_with_sonnet5_compat  # type: ignore[method-assign]
