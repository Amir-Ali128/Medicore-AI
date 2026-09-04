"""Runtime resilience primitives for expensive/external dependencies.

The guard deliberately lives below domain logic so every AI/model caller can share
bounded concurrency, a hard wall-clock timeout and a small circuit breaker without
re-implementing them. It contains no clinical rules and never converts dependency
success into clinical confidence.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from app.core.config import get_settings

T = TypeVar("T")


class DependencyGuardError(RuntimeError):
    """Base class for controlled external-dependency failures."""


class DependencyBusyError(DependencyGuardError):
    """Raised when the concurrency queue cannot be entered quickly enough."""


class DependencyTimeoutError(DependencyGuardError):
    """Raised when an admitted dependency call exceeds its hard timeout."""


class DependencyCircuitOpenError(DependencyGuardError):
    """Raised when recent failures have opened the circuit breaker."""


class DependencyCallError(DependencyGuardError):
    """Raised when the guarded dependency itself raises an exception."""


@dataclass(frozen=True)
class _CircuitProbe:
    half_open: bool = False


class CircuitBreaker:
    """Small process-local consecutive-failure circuit breaker.

    Closed -> open after ``failure_threshold`` consecutive failures. Once the
    recovery window expires exactly one half-open probe is allowed through. A
    successful probe closes the breaker; a failed probe re-opens it.
    """

    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1.")
        if recovery_seconds <= 0:
            raise ValueError("recovery_seconds must be positive.")
        self.failure_threshold = int(failure_threshold)
        self.recovery_seconds = float(recovery_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False

    def assert_available(self) -> None:
        """Fail fast for a definitely-open circuit without reserving a probe."""
        now = self._clock()
        with self._lock:
            if self._opened_at is None:
                return
            elapsed = now - self._opened_at
            if elapsed < self.recovery_seconds:
                remaining = max(0.0, self.recovery_seconds - elapsed)
                raise DependencyCircuitOpenError(
                    f"Dependency circuit is open for another {remaining:.2f}s."
                )
            if self._half_open_in_flight:
                raise DependencyCircuitOpenError(
                    "Dependency circuit is half-open and already has a probe in flight."
                )

    def before_call(self) -> _CircuitProbe:
        now = self._clock()
        with self._lock:
            if self._opened_at is None:
                return _CircuitProbe(False)

            elapsed = now - self._opened_at
            if elapsed < self.recovery_seconds:
                remaining = max(0.0, self.recovery_seconds - elapsed)
                raise DependencyCircuitOpenError(
                    f"Dependency circuit is open for another {remaining:.2f}s."
                )

            if self._half_open_in_flight:
                raise DependencyCircuitOpenError(
                    "Dependency circuit is half-open and already has a probe in flight."
                )

            self._half_open_in_flight = True
            return _CircuitProbe(True)

    def record_success(self, probe: _CircuitProbe) -> None:
        del probe
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_in_flight = False

    def record_failure(self, probe: _CircuitProbe) -> None:
        now = self._clock()
        with self._lock:
            if probe.half_open:
                self._consecutive_failures = max(
                    self._consecutive_failures,
                    self.failure_threshold,
                )
                self._opened_at = now
                self._half_open_in_flight = False
                return

            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._opened_at = now
            self._half_open_in_flight = False

    def cancel_probe(self, probe: _CircuitProbe) -> None:
        if not probe.half_open:
            return
        with self._lock:
            self._half_open_in_flight = False

    def snapshot(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            opened_at = self._opened_at
            half_open = self._half_open_in_flight
            failures = self._consecutive_failures

        if opened_at is None:
            state = "closed"
            retry_after = 0.0
        else:
            elapsed = max(0.0, now - opened_at)
            retry_after = max(0.0, self.recovery_seconds - elapsed)
            state = "open" if retry_after > 0 else "half_open"

        return {
            "state": state,
            "consecutive_failures": failures,
            "failure_threshold": self.failure_threshold,
            "recovery_seconds": self.recovery_seconds,
            "retry_after_seconds": round(retry_after, 3),
            "half_open_probe_in_flight": half_open,
        }


class AsyncDependencyGuard:
    """Bound async dependency execution by queue, timeout and circuit state."""

    def __init__(
        self,
        name: str,
        *,
        timeout_seconds: float,
        queue_timeout_seconds: float,
        max_concurrency: int,
        failure_threshold: int,
        recovery_seconds: float,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Dependency guard name cannot be empty.")
        if timeout_seconds <= 0 or queue_timeout_seconds <= 0:
            raise ValueError("Dependency timeouts must be positive.")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1.")

        self.name = clean_name
        self.timeout_seconds = float(timeout_seconds)
        self.queue_timeout_seconds = float(queue_timeout_seconds)
        self.max_concurrency = int(max_concurrency)
        self.breaker = breaker or CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_seconds=recovery_seconds,
        )
        self._state_lock = threading.Lock()
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.BoundedSemaphore | None = None
        self._in_flight = 0
        self._admitted_total = 0
        self._success_total = 0
        self._failure_total = 0
        self._timeout_total = 0
        self._busy_total = 0

    @property
    def config_signature(self) -> tuple[float, float, int, int, float]:
        return (
            self.timeout_seconds,
            self.queue_timeout_seconds,
            self.max_concurrency,
            self.breaker.failure_threshold,
            self.breaker.recovery_seconds,
        )

    def _semaphore_for_running_loop(self) -> asyncio.BoundedSemaphore:
        loop = asyncio.get_running_loop()
        with self._state_lock:
            if self._semaphore is None or self._semaphore_loop is not loop:
                if self._in_flight:
                    raise RuntimeError(
                        "Dependency guard cannot move event loops while calls are in flight."
                    )
                self._semaphore_loop = loop
                self._semaphore = asyncio.BoundedSemaphore(self.max_concurrency)
            return self._semaphore

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Execute one dependency call with bounded queueing and a hard timeout."""

        self.breaker.assert_available()
        semaphore = self._semaphore_for_running_loop()
        try:
            await asyncio.wait_for(
                semaphore.acquire(),
                timeout=self.queue_timeout_seconds,
            )
        except TimeoutError as exc:
            with self._state_lock:
                self._busy_total += 1
            raise DependencyBusyError(
                f"{self.name} concurrency limit is saturated."
            ) from exc

        probe: _CircuitProbe | None = None
        with self._state_lock:
            self._in_flight += 1
            self._admitted_total += 1

        try:
            probe = self.breaker.before_call()
            try:
                result = await asyncio.wait_for(
                    operation(),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                self.breaker.record_failure(probe)
                with self._state_lock:
                    self._failure_total += 1
                    self._timeout_total += 1
                raise DependencyTimeoutError(
                    f"{self.name} exceeded {self.timeout_seconds:.2f}s timeout."
                ) from exc
            except asyncio.CancelledError:
                self.breaker.cancel_probe(probe)
                raise
            except Exception as exc:
                self.breaker.record_failure(probe)
                with self._state_lock:
                    self._failure_total += 1
                raise DependencyCallError(f"{self.name} call failed.") from exc

            self.breaker.record_success(probe)
            with self._state_lock:
                self._success_total += 1
            return result
        finally:
            with self._state_lock:
                self._in_flight -= 1
            semaphore.release()

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            counters = {
                "in_flight": self._in_flight,
                "admitted_total": self._admitted_total,
                "success_total": self._success_total,
                "failure_total": self._failure_total,
                "timeout_total": self._timeout_total,
                "busy_total": self._busy_total,
            }
        return {
            "name": self.name,
            "timeout_seconds": self.timeout_seconds,
            "queue_timeout_seconds": self.queue_timeout_seconds,
            "max_concurrency": self.max_concurrency,
            **counters,
            "circuit": self.breaker.snapshot(),
        }


_GUARDS: dict[str, AsyncDependencyGuard] = {}
_GUARDS_LOCK = threading.Lock()


def get_dependency_guard(
    name: str,
    *,
    timeout_seconds: float,
    queue_timeout_seconds: float,
    max_concurrency: int,
    failure_threshold: int,
    recovery_seconds: float,
) -> AsyncDependencyGuard:
    signature = (
        float(timeout_seconds),
        float(queue_timeout_seconds),
        int(max_concurrency),
        int(failure_threshold),
        float(recovery_seconds),
    )
    with _GUARDS_LOCK:
        existing = _GUARDS.get(name)
        if existing is not None and existing.config_signature == signature:
            return existing
        replacement = AsyncDependencyGuard(
            name,
            timeout_seconds=signature[0],
            queue_timeout_seconds=signature[1],
            max_concurrency=signature[2],
            failure_threshold=signature[3],
            recovery_seconds=signature[4],
        )
        _GUARDS[name] = replacement
        return replacement


def _provider_guard(provider: str, workload: str) -> AsyncDependencyGuard:
    settings = get_settings()
    return get_dependency_guard(
        f"{provider}:{str(workload).strip() or 'default'}",
        timeout_seconds=settings.ai_call_timeout_seconds,
        queue_timeout_seconds=settings.ai_queue_timeout_seconds,
        max_concurrency=settings.ai_max_concurrency,
        failure_threshold=settings.ai_circuit_breaker_failures,
        recovery_seconds=settings.ai_circuit_breaker_recovery_seconds,
    )


def get_anthropic_guard(workload: str) -> AsyncDependencyGuard:
    return _provider_guard("anthropic", workload)


def get_openai_guard(workload: str) -> AsyncDependencyGuard:
    return _provider_guard("openai", workload)


def get_gemini_guard(workload: str) -> AsyncDependencyGuard:
    return _provider_guard("gemini", workload)


def registered_dependency_snapshots() -> dict[str, dict[str, Any]]:
    with _GUARDS_LOCK:
        guards = list(_GUARDS.items())
    return {name: guard.snapshot() for name, guard in guards}


def reset_dependency_guards_for_tests() -> None:
    """Clear process-local guards. Intended only for deterministic unit tests."""
    with _GUARDS_LOCK:
        _GUARDS.clear()
