from app.domain.claude_sonnet5_compat_runtime import _compatible_kwargs


def test_sonnet5_removes_sampling_and_disables_thinking() -> None:
    kwargs = _compatible_kwargs(
        {
            "model": "claude-sonnet-5",
            "max_tokens": 120,
            "temperature": 0,
            "top_p": 0.9,
            "top_k": 10,
        }
    )

    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "top_k" not in kwargs
    assert kwargs["thinking"] == {"type": "disabled"}
    assert kwargs["max_tokens"] == 120


def test_older_model_request_is_not_rewritten() -> None:
    original = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 120,
        "temperature": 0,
    }

    assert _compatible_kwargs(original) == original
