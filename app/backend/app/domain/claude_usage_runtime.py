"""Capture Anthropic usage for compact Claude evaluations.

The compact clinical service keeps its prompt tiny. This runtime extension records
Anthropic's response usage on successful calls and stores an estimated USD cost in
the hypothesis metadata for admin-only analytics. No prompt or patient data is
added to analytics.
"""

from __future__ import annotations

from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService

_SONNET_5_INPUT_PER_MILLION_USD = 2.0
_SONNET_5_OUTPUT_PER_MILLION_USD = 10.0

_original_init = ClaudeClinicalHypothesisService.__init__
_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis


def _usage_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens * _SONNET_5_INPUT_PER_MILLION_USD / 1_000_000)
        + (output_tokens * _SONNET_5_OUTPUT_PER_MILLION_USD / 1_000_000),
        8,
    )


class _MessagesUsageProxy:
    def __init__(self, owner: ClaudeClinicalHypothesisService, messages: Any) -> None:
        self._owner = owner
        self._messages = messages

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        self._owner._last_claude_usage = None
        response = await self._messages.create(*args, **kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            self._owner._last_claude_usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": _usage_cost_usd(input_tokens, output_tokens),
                "input_price_per_million_usd": _SONNET_5_INPUT_PER_MILLION_USD,
                "output_price_per_million_usd": _SONNET_5_OUTPUT_PER_MILLION_USD,
                "usage_source": "anthropic_response",
            }
        return response


class _ClientUsageProxy:
    def __init__(self, owner: ClaudeClinicalHypothesisService, client: Any) -> None:
        self._client = client
        self.messages = _MessagesUsageProxy(owner, client.messages)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def _init_with_usage_tracking(self: ClaudeClinicalHypothesisService, *args: Any, **kwargs: Any) -> None:
    _original_init(self, *args, **kwargs)
    self._last_claude_usage = None
    self._client = _ClientUsageProxy(self, self._client)


def _build_hypothesis_with_usage(
    self: ClaudeClinicalHypothesisService,
    run: Any,
    *,
    risk: int,
    summary: str,
    flags: list[str],
    symptoms: list[str],
    evidence: list[dict[str, Any]],
    ai_called: bool,
):
    hypothesis = _original_build_hypothesis(
        self,
        run,
        risk=risk,
        summary=summary,
        flags=flags,
        symptoms=symptoms,
        evidence=evidence,
        ai_called=ai_called,
    )
    metadata = dict(hypothesis.metadata_json or {})
    usage = getattr(self, "_last_claude_usage", None)
    if ai_called and isinstance(usage, dict):
        metadata["claude_usage"] = usage
    else:
        metadata["claude_usage"] = None
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService.__init__ = _init_with_usage_tracking
ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_usage
