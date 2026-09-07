"""Crash-isolation helpers for optional native C++ extensions.

A segmentation fault in a pybind module terminates the hosting Python process. For
untrusted/externally supplied payloads, MediCore can execute one native call in a short-
lived spawned subprocess. The parent detects native crashes/timeouts and remains alive.
"""

from __future__ import annotations

import importlib
import multiprocessing as mp
import os
from multiprocessing.connection import Connection
from typing import Any


class NativeProcessError(RuntimeError):
    """Base error for isolated native execution failures."""


class NativeProcessCrashed(NativeProcessError):
    """The native worker exited without a valid response (including signals/segfaults)."""


class NativeProcessTimeout(NativeProcessError):
    """The native worker exceeded its execution deadline."""


def _env_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def native_process_isolation_enabled() -> bool:
    return _env_enabled(os.getenv("MEDICORE_NATIVE_PROCESS_ISOLATION", "0"))


def _worker_entry(
    connection: Connection,
    module_name: str,
    function_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        result = function(*args, **kwargs)
        connection.send(("ok", result))
    except BaseException as exc:  # child must serialize ordinary Python/native exceptions
        try:
            connection.send(("error", exc.__class__.__name__, str(exc)[:1000]))
        except BaseException:
            pass
    finally:
        connection.close()


def isolated_native_call(
    module_name: str,
    function_name: str,
    *args: Any,
    timeout_seconds: float = 15.0,
    **kwargs: Any,
) -> Any:
    """Execute a module function in a spawned process and survive native crashes."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds pozitif olmalıdır.")
    if not module_name or not function_name:
        raise ValueError("module_name ve function_name zorunludur.")

    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker_entry,
        args=(child, module_name, function_name, tuple(args), dict(kwargs)),
        daemon=True,
        name=f"medicore-native:{module_name}.{function_name}",
    )
    process.start()
    child.close()

    try:
        if not parent.poll(float(timeout_seconds)):
            if process.is_alive():
                process.terminate()
            process.join(timeout=2.0)
            if process.is_alive():
                process.kill()
                process.join(timeout=1.0)
            raise NativeProcessTimeout(
                f"Native call timed out after {timeout_seconds:g}s: {module_name}.{function_name}"
            )

        try:
            message = parent.recv()
        except EOFError as exc:
            process.join(timeout=1.0)
            raise NativeProcessCrashed(
                f"Native worker exited without response (exitcode={process.exitcode}): "
                f"{module_name}.{function_name}"
            ) from exc
        process.join(timeout=2.0)

        if not isinstance(message, tuple) or not message:
            raise NativeProcessCrashed("Native worker returned an invalid response envelope.")
        if message[0] == "ok":
            return message[1]
        if message[0] == "error":
            error_type = str(message[1]) if len(message) > 1 else "Exception"
            detail = str(message[2]) if len(message) > 2 else ""
            raise NativeProcessError(
                f"Native worker error {error_type}: {detail}"
            )
        raise NativeProcessCrashed("Native worker returned an unknown response envelope.")
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)


def _probe_native_modules() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    probes = {
        "lab": ("medicore_lab", "CONTRACT_VERSION"),
        "lab_extensions": ("medicore_lab_ext", "EXTENSIONS_VERSION"),
        "vision": ("medicore_vision", "__version__"),
        "onnx": ("medicore_onnx", "CONTRACT_VERSION"),
    }
    for name, (module_name, version_attr) in probes.items():
        try:
            module = importlib.import_module(module_name)
            item: dict[str, Any] = {
                "status": "ok",
                "version": str(getattr(module, version_attr, "unknown")),
            }
            if module_name == "medicore_onnx":
                runtime_available = getattr(module, "runtime_available", None)
                item["runtime_available"] = bool(
                    callable(runtime_available) and runtime_available()
                )
            if module_name == "medicore_vision":
                codec_fn = getattr(module, "dicom_codec_capabilities", None)
                if callable(codec_fn):
                    item["dicom_codecs"] = dict(codec_fn())
            result[name] = item
        except (ImportError, OSError, RuntimeError, AttributeError) as exc:
            result[name] = {
                "status": "unavailable",
                "error_type": exc.__class__.__name__,
            }
    return result


def probe_native_extensions(*, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Probe native modules in a child so a bad extension cannot kill readiness."""
    try:
        modules = isolated_native_call(
            __name__,
            "_probe_native_modules",
            timeout_seconds=timeout_seconds,
        )
    except NativeProcessTimeout:
        return {"status": "timeout", "critical": False, "modules": {}}
    except NativeProcessError as exc:
        return {
            "status": "degraded",
            "critical": False,
            "error_type": exc.__class__.__name__,
            "modules": {},
        }

    if not isinstance(modules, dict):
        return {"status": "degraded", "critical": False, "modules": {}}
    unavailable = [
        name for name, item in modules.items()
        if not isinstance(item, dict) or item.get("status") != "ok"
    ]
    return {
        "status": "degraded" if unavailable else "ok",
        "critical": False,
        "modules": modules,
        "unavailable": sorted(unavailable),
    }
