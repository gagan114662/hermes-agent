"""
Metrics collection for Hermes Agent.

Tracks tool invocations, response times, and error rates in memory.
Thread-safe.  Zero external dependencies.

Usage:
    from tools.metrics import METRICS

    # Record a tool execution (called automatically by registry.dispatch)
    METRICS.record("terminal", duration_ms=42.3, success=True)

    # Read a snapshot (e.g. for the health endpoint)
    snap = METRICS.snapshot()
    # {
    #   "uptime_s": 3600,
    #   "total_calls": 412,
    #   "total_errors": 7,
    #   "error_rate": 0.017,
    #   "tools": {
    #       "terminal": {
    #           "calls": 100, "errors": 2, "error_rate": 0.02,
    #           "p50_ms": 45.1, "p95_ms": 120.3, "p99_ms": 210.0,
    #           "mean_ms": 55.2
    #       },
    #       ...
    #   }
    # }

    # Prometheus text format (for /metrics endpoint)
    print(METRICS.prometheus())
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, List

# Maximum number of duration samples kept per tool (ring-buffer style)
_MAX_SAMPLES = 1000


class MetricsCollector:
    """In-memory, thread-safe metrics store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time: float = time.monotonic()
        self._calls: Dict[str, int] = defaultdict(int)
        self._errors: Dict[str, int] = defaultdict(int)
        # Deque-like ring buffer: list + head pointer per tool
        self._durations: Dict[str, List[float]] = defaultdict(list)
        self._duration_head: Dict[str, int] = defaultdict(int)

    # ── recording ─────────────────────────────────────────────────────────

    def record(self, tool: str, duration_ms: float, *, success: bool = True) -> None:
        """
        Record a single tool execution.

        Args:
            tool:        Tool name (e.g. ``"terminal"``).
            duration_ms: Wall-clock execution time in milliseconds.
            success:     ``False`` if the tool raised an exception or
                         returned an ``{"error": ...}`` response.
        """
        with self._lock:
            self._calls[tool] += 1
            if not success:
                self._errors[tool] += 1

            buf = self._durations[tool]
            if len(buf) < _MAX_SAMPLES:
                buf.append(duration_ms)
            else:
                head = self._duration_head[tool]
                buf[head % _MAX_SAMPLES] = duration_ms
                self._duration_head[tool] = head + 1

    # ── percentile helper ─────────────────────────────────────────────────

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        sorted_v = sorted(values)
        idx = max(0, int(len(sorted_v) * pct / 100) - 1)
        return round(sorted_v[idx], 2)

    # ── snapshot ──────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """
        Return a point-in-time metrics snapshot as a plain dict.

        Suitable for serialising to JSON (e.g. in a health endpoint).
        """
        with self._lock:
            calls = dict(self._calls)
            errors = dict(self._errors)
            durations = {k: list(v) for k, v in self._durations.items()}

        total_calls = sum(calls.values())
        total_errors = sum(errors.values())
        uptime_s = round(time.monotonic() - self._start_time, 1)

        tools: dict = {}
        for tool in sorted(calls):
            n = calls[tool]
            e = errors.get(tool, 0)
            d = durations.get(tool, [])
            mean_ms = round(sum(d) / len(d), 2) if d else 0.0
            tools[tool] = {
                "calls": n,
                "errors": e,
                "error_rate": round(e / n, 4) if n else 0.0,
                "p50_ms": self._percentile(d, 50),
                "p95_ms": self._percentile(d, 95),
                "p99_ms": self._percentile(d, 99),
                "mean_ms": mean_ms,
            }

        return {
            "uptime_s": uptime_s,
            "total_calls": total_calls,
            "total_errors": total_errors,
            "error_rate": round(total_errors / total_calls, 4) if total_calls else 0.0,
            "tools": tools,
        }

    # ── prometheus text format ────────────────────────────────────────────

    def prometheus(self) -> str:
        """
        Return metrics in Prometheus text exposition format.

        Suitable for scraping by Prometheus or a compatible agent.
        """
        snap = self.snapshot()
        lines: list[str] = [
            "# HELP hermes_uptime_seconds Seconds since process start",
            "# TYPE hermes_uptime_seconds gauge",
            f"hermes_uptime_seconds {snap['uptime_s']}",
            "",
            "# HELP hermes_tool_calls_total Total tool invocations",
            "# TYPE hermes_tool_calls_total counter",
        ]
        for tool, stats in snap["tools"].items():
            label = f'tool="{tool}"'
            lines.append(f"hermes_tool_calls_total{{{label}}} {stats['calls']}")

        lines += [
            "",
            "# HELP hermes_tool_errors_total Total tool execution errors",
            "# TYPE hermes_tool_errors_total counter",
        ]
        for tool, stats in snap["tools"].items():
            label = f'tool="{tool}"'
            lines.append(f"hermes_tool_errors_total{{{label}}} {stats['errors']}")

        lines += [
            "",
            "# HELP hermes_tool_duration_p50_ms P50 tool execution latency (ms)",
            "# TYPE hermes_tool_duration_p50_ms gauge",
        ]
        for tool, stats in snap["tools"].items():
            label = f'tool="{tool}"'
            lines.append(f"hermes_tool_duration_p50_ms{{{label}}} {stats['p50_ms']}")

        lines += [
            "",
            "# HELP hermes_tool_duration_p95_ms P95 tool execution latency (ms)",
            "# TYPE hermes_tool_duration_p95_ms gauge",
        ]
        for tool, stats in snap["tools"].items():
            label = f'tool="{tool}"'
            lines.append(f"hermes_tool_duration_p95_ms{{{label}}} {stats['p95_ms']}")

        lines.append("")
        return "\n".join(lines)

    # ── reset (test helper) ───────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all metrics.  Intended for tests."""
        with self._lock:
            self._start_time = time.monotonic()
            self._calls.clear()
            self._errors.clear()
            self._durations.clear()
            self._duration_head.clear()


# Global singleton — import this everywhere
METRICS: MetricsCollector = MetricsCollector()
