from app.domain.claude_usage_runtime import _usage_cost_usd


def test_sonnet_5_usage_cost_uses_current_per_million_rates() -> None:
    assert _usage_cost_usd(250, 50) == 0.001


def test_zero_usage_cost_is_zero() -> None:
    assert _usage_cost_usd(0, 0) == 0.0


def test_usage_cost_keeps_micro_cost_precision() -> None:
    assert _usage_cost_usd(200, 25) == 0.00065
