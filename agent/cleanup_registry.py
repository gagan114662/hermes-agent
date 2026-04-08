"""
Global cleanup function registry.

Register cleanup callables that run on SIGTERM/SIGINT.
All cleanups run with a 2s timeout (parallel via threads).
"""
from __future__ import annotations
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait

logger = logging.getLogger(__name__)

_cleanups: set[Callable[[], None]] = set()
_lock = threading.Lock()


def register_cleanup(fn: Callable[[], None]) -> Callable[[], None]:
    """Register a cleanup fn. Returns an unregister callable."""
    with _lock:
        _cleanups.add(fn)
    return lambda: _unregister(fn)


def _unregister(fn: Callable[[], None]) -> None:
    with _lock:
        _cleanups.discard(fn)


def run_all_cleanups(timeout: float = 2.0) -> None:
    """Run all registered cleanup fns in parallel with timeout. Never raises."""
    with _lock:
        fns = list(_cleanups)
    if not fns:
        return
    logger.debug("Running %d cleanup functions (timeout=%.1fs)", len(fns), timeout)
    try:
        with ThreadPoolExecutor(max_workers=len(fns)) as ex:
            futures = [ex.submit(_safe_run, fn) for fn in fns]
            futures_wait(futures, timeout=timeout)
    except Exception as e:
        logger.debug("Cleanup registry error: %s", e)


def _safe_run(fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception as e:
        logger.debug("Cleanup fn %s raised: %s", getattr(fn, '__name__', fn), e)
