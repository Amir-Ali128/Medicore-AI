from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.runtime_health import (
    compose_readiness_snapshot,
    reset_runtime_health_for_tests,
    run_noncritical_startup_step,
    runtime_component_snapshots,
)
from app.infrastructure.runtime_resilience import (
    AsyncDependencyGuard,
    CircuitBreaker,
    DependencyBusyError,
    DependencyCircuitOpenError,
    DependencyTimeoutError,
)


def test_circuit_breaker_opens_then_recovers_through_half_open_probe():
    now = [0.0]
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_seconds=5.0,
        clock=lambda: now[0],
    )

    first = breaker.before_call()
    breaker.record_failure(first)
    assert breaker.snapshot()["state"] == "closed"

    second = breaker.before_call()
    breaker.record_failure(second)
    assert breaker.snapshot()["state"] == "open"

    with pytest.raises(DependencyCircuitOpenError):
        breaker.before_call()

    now[0] = 6.0
    probe = breaker.before_call()
    assert probe.half_open is True
    assert breaker.snapshot()["state"] == "half_open"

    breaker.record_success(probe)
    snapshot = breaker.snapshot()
    assert snapshot["state"] == "closed"
    assert snapshot["consecutive_failures"] == 0


def test_dependency_guard_times_out_and_opens_circuit():
    async def scenario() -> None:
        guard = AsyncDependencyGuard(
            "slow-provider",
            timeout_seconds=0.01,
            queue_timeout_seconds=0.01,
            max_concurrency=1,
            failure_threshold=1,
            recovery_seconds=10.0,
        )

        async def slow() -> str:
            await asyncio.sleep(0.05)
            return "late"

        with pytest.raises(DependencyTimeoutError):
            await guard.call(slow)

        snapshot = guard.snapshot()
        assert snapshot["timeout_total"] == 1
        assert snapshot["failure_total"] == 1
        assert snapshot["in_flight"] == 0
        assert snapshot["circuit"]["state"] == "open"

        with pytest.raises(DependencyCircuitOpenError):
            await guard.call(lambda: asyncio.sleep(0))

    asyncio.run(scenario())


def test_dependency_guard_rejects_excess_concurrency_without_leaking_slot():
    async def scenario() -> None:
        guard = AsyncDependencyGuard(
            "capacity-provider",
            timeout_seconds=1.0,
            queue_timeout_seconds=0.01,
            max_concurrency=1,
            failure_threshold=3,
            recovery_seconds=10.0,
        )
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold() -> str:
            entered.set()
            await release.wait()
            return "ok"

        task = asyncio.create_task(guard.call(hold))
        await entered.wait()

        with pytest.raises(DependencyBusyError):
            await guard.call(lambda: asyncio.sleep(0))

        release.set()
        assert await task == "ok"
        snapshot = guard.snapshot()
        assert snapshot["busy_total"] == 1
        assert snapshot["success_total"] == 1
        assert snapshot["in_flight"] == 0

    asyncio.run(scenario())


def test_readiness_stays_available_when_only_optional_ai_circuit_is_open():
    snapshot = compose_readiness_snapshot(
        database={"status": "ok", "critical": True},
        dependency_guards={
            "anthropic:radiology-media": {
                "circuit": {"state": "open"},
            }
        },
        runtime_components={},
    )

    assert snapshot["ready"] is True
    assert snapshot["status"] == "degraded"
    assert snapshot["degraded_optional_dependencies"] == [
        "anthropic:radiology-media"
    ]


def test_readiness_fails_when_database_is_unavailable():
    snapshot = compose_readiness_snapshot(
        database={"status": "unavailable", "critical": True},
        dependency_guards={},
        runtime_components={},
    )

    assert snapshot["ready"] is False
    assert snapshot["status"] == "not_ready"


def test_noncritical_startup_failure_is_isolated_and_reported():
    async def scenario() -> None:
        reset_runtime_health_for_tests()

        async def boom() -> None:
            raise RuntimeError("secret provider detail")

        result = await run_noncritical_startup_step("optional-cleanup", boom)
        assert result is None
        component = runtime_component_snapshots()["optional-cleanup"]
        assert component["status"] == "degraded"
        assert component["critical"] is False
        assert component["detail"] == "RuntimeError"
        assert "secret provider detail" not in str(component)

    asyncio.run(scenario())


def test_production_limits_reject_unbounded_configuration():
    with pytest.raises(ValidationError):
        Settings(ai_max_concurrency=0)
    with pytest.raises(ValidationError):
        Settings(ai_call_timeout_seconds=9999)
    with pytest.raises(ValidationError):
        Settings(radiology_image_max_bytes=100 * 1024 * 1024)
    with pytest.raises(ValidationError):
        Settings(onnx_intra_op_threads=0)
