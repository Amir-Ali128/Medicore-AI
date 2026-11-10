"""Serialize heavyweight local inference and evict inactive model caches."""
from threading import RLock
import ctypes
import gc

model_lock = RLock()
_releasers = {}
_active = None


def register_model(name, release):
    _releasers[name] = release


def activate_model(name):
    """Caller must hold model_lock throughout initialization and inference."""
    global _active
    if _active == name:
        return
    for other, release in _releasers.items():
        if other != name:
            release()
    gc.collect()
    # Return freed native allocations to the OS on Linux; optional elsewhere.
    try:
        ctypes.CDLL(None).malloc_trim(0)
    except (AttributeError, OSError):
        pass
    _active = name
