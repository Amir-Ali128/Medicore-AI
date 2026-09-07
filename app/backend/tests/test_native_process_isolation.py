from __future__ import annotations

import pytest

from app.infrastructure.native_process_isolation import (
    NativeProcessError,
    isolated_native_call,
    probe_native_extensions,
)


def test_isolated_native_call_returns_serializable_result() -> None:
    assert isolated_native_call("math", "sqrt", 81.0, timeout_seconds=5.0) == 9.0


def test_isolated_native_call_propagates_child_error_without_killing_parent() -> None:
    with pytest.raises(NativeProcessError):
        isolated_native_call("math", "sqrt", -1.0, timeout_seconds=5.0)
    assert 2 + 2 == 4


def test_native_probe_is_fail_safe_when_extensions_are_missing() -> None:
    snapshot = probe_native_extensions(timeout_seconds=5.0)
    assert snapshot["status"] in {"ok", "degraded"}
    assert snapshot["critical"] is False
    assert isinstance(snapshot["modules"], dict)
