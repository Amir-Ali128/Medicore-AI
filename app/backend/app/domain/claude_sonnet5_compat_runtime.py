"""Claude 5 request compatibility and diagnostics.

Current Claude 5 models reject legacy non-default sampling parameters such as
``temperature=0`` and may run adaptive thinking by default. MediCore still has a
few compact clinical/radiology call sites that send those legacy knobs, so this
runtime shim normalizes requests before they reach the Anthropic SDK.

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


def _is_claude5(model: object) -> bool:
    normalized = str(model or "").strip().lower()
    return normalized.startswith("claude-sonnet-5") or normalized.startswith("claude-opus-5")


def _compatible_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return request kwargs compatible with Claude 5 inference."""

    adjusted = dict(kwargs)
    if not _is_claude5(adjusted.get("model")):
        return adjusted

    # Claude 5 rejects deprecated/non-default sampling values with HTTP 400.
    # Radiology document/image review historically sent temperature=0; removing
    # these knobs lets the provider use the model's supported defaults.
    adjusted.pop("temperature", None)
    adjusted.pop("top_p", None)
    adjusted.pop("top_k", None)

    # Adaptive thinking can consume the output budget of compact JSON calls.
    # Explicitly disable it for these legacy request shapes so both radiology and
    # clinical synthesis receive a predictable response budget.
    adjusted.setdefault("thinking", {"type": "disabled"})
    return adjusted


async def _create_with_claude5_compat(self: Any, *args: Any, **kwargs: Any) -> Any:
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


if not getattr(AsyncMessages.create, "_medicore_claude5_compat", False):
    setattr(_create_with_claude5_compat, "_medicore_claude5_compat", True)
    AsyncMessages.create = _create_with_claude5_compat  # type: ignore[method-assign]
