"""
Prevent macOS from sleeping during long agent tasks.

Reference-counted API: multiple concurrent sessions safe.
Uses caffeinate -i -t 300 with 4-minute restart interval.
macOS only (no-op on other platforms).
"""
import subprocess
import sys
import threading
import logging

logger = logging.getLogger(__name__)

_ref_count = 0
_lock = threading.Lock()
_process: subprocess.Popen | None = None
_restart_timer: threading.Timer | None = None
_cleanup_registered = False

CAFFEINATE_TIMEOUT_SECS = 300   # 5 minutes
RESTART_INTERVAL_SECS = 240     # 4 minutes (before expiry)


def start_prevent_sleep() -> None:
    """Increment ref count. Spawn caffeinate on first call."""
    global _ref_count

    with _lock:
        _ref_count += 1
        first = _ref_count == 1

    if first:
        _spawn_caffeinate()
        _start_restart_timer()


def stop_prevent_sleep() -> None:
    """Decrement ref count. Kill caffeinate when reaches zero."""
    global _ref_count

    with _lock:
        if _ref_count > 0:
            _ref_count -= 1
        reached_zero = _ref_count == 0

    if reached_zero:
        _stop_restart_timer()
        _kill_caffeinate()


def force_stop_prevent_sleep() -> None:
    """Force stop regardless of ref count. Used by cleanup registry."""
    global _ref_count

    with _lock:
        _ref_count = 0

    _stop_restart_timer()
    _kill_caffeinate()


def _spawn_caffeinate() -> None:
    global _process, _cleanup_registered

    if sys.platform != 'darwin':
        return

    with _lock:
        if _process is not None:
            return
        already_registered = _cleanup_registered
        if not already_registered:
            _cleanup_registered = True

    # Register cleanup on first spawn (outside of lock to avoid potential deadlock)
    if not already_registered:
        try:
            from agent.cleanup_registry import register_cleanup
            register_cleanup(force_stop_prevent_sleep)
        except ImportError:
            logger.debug("Could not register cleanup for prevent_sleep")

    try:
        proc = subprocess.Popen(
            ['caffeinate', '-i', '-t', str(CAFFEINATE_TIMEOUT_SECS)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with _lock:
            _process = proc
        logger.debug("Started caffeinate to prevent sleep (pid=%d)", proc.pid)
    except Exception as e:
        logger.debug("caffeinate spawn failed: %s", e)


def _kill_caffeinate() -> None:
    global _process

    with _lock:
        proc = _process
        _process = None

    if proc is not None:
        try:
            proc.terminate()
            logger.debug("Stopped caffeinate, allowing sleep")
        except Exception as e:
            logger.debug("caffeinate terminate error: %s", e)


def _start_restart_timer() -> None:
    global _restart_timer

    if sys.platform != 'darwin':
        return

    with _lock:
        if _restart_timer is not None:
            return

    def _restart() -> None:
        global _ref_count
        with _lock:
            count = _ref_count
        if count > 0:
            logger.debug("Restarting caffeinate to maintain sleep prevention")
            _kill_caffeinate()
            _spawn_caffeinate()
        _start_restart_timer()

    timer = threading.Timer(RESTART_INTERVAL_SECS, _restart)
    timer.daemon = True
    with _lock:
        _restart_timer = timer
    timer.start()


def _stop_restart_timer() -> None:
    global _restart_timer

    with _lock:
        timer = _restart_timer
        _restart_timer = None

    if timer is not None:
        timer.cancel()
