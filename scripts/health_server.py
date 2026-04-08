#!/usr/bin/env python3
"""
Standalone health-check HTTP server for Hermes Agent.

Exposes two endpoints on a configurable port (default 9090):

    GET /health   — JSON health snapshot  (for load-balancers / uptime monitors)
    GET /ready    — 200 OK when agent is ready, 503 when not  (k8s readiness probe)
    GET /metrics  — Prometheus text-format metrics  (for Prometheus/Grafana)

Usage:
    python3 scripts/health_server.py             # port 9090
    python3 scripts/health_server.py --port 8080
    HERMES_HEALTH_PORT=8080 python3 scripts/health_server.py

    # From code (e.g. start alongside the gateway):
    from scripts.health_server import start_health_server
    thread = start_health_server(port=9090)  # non-blocking daemon thread
"""

from __future__ import annotations

import argparse
import http.server
import json
import logging
import os
import sys
import threading
from pathlib import Path

# Ensure project root is importable when run as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)

DEFAULT_PORT = int(os.environ.get("HERMES_HEALTH_PORT", "9090"))


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("hermes-agent")
    except Exception:
        return "unknown"


def _metrics_snapshot() -> dict:
    """Return the current METRICS snapshot (graceful no-op if unavailable)."""
    try:
        from tools.metrics import METRICS
        return METRICS.snapshot()
    except Exception:
        return {"error": "metrics unavailable"}


def _prometheus_text() -> str:
    """Return Prometheus-format metrics text."""
    try:
        from tools.metrics import METRICS
        return METRICS.prometheus()
    except Exception:
        return "# metrics unavailable\n"


def _sentry_status() -> str:
    try:
        from hermes_cli.sentry import is_configured
        return "enabled" if is_configured() else "disabled"
    except Exception:
        return "unknown"


# ── request handler ───────────────────────────────────────────────────────────

class _HealthHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP/1.1 handler for health and metrics endpoints."""

    # Suppress the default access log to stderr
    def log_message(self, fmt: str, *args: object) -> None:
        logger.debug("health_server: " + fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/") or "/"

        if path == "/health":
            self._health()
        elif path == "/ready":
            self._ready()
        elif path == "/metrics":
            self._metrics()
        else:
            self._not_found()

    # ── endpoint implementations ──────────────────────────────────────────

    def _health(self) -> None:
        snap = _metrics_snapshot()
        body = {
            "status": "ok",
            "version": _get_version(),
            "sentry": _sentry_status(),
            "metrics": snap,
        }
        self._send_json(200, body)

    def _ready(self) -> None:
        """Readiness probe: 200 when healthy, 503 on degraded state."""
        snap = _metrics_snapshot()
        error_rate = snap.get("error_rate", 0.0)
        # Consider unhealthy if global error rate exceeds 50%
        if error_rate > 0.5 and snap.get("total_calls", 0) > 10:
            self._send_json(503, {"status": "degraded", "error_rate": error_rate})
        else:
            self._send_json(200, {"status": "ready"})

    def _metrics(self) -> None:
        text = _prometheus_text()
        self._send_text(200, text, content_type="text/plain; version=0.0.4; charset=utf-8")

    def _not_found(self) -> None:
        self._send_json(404, {
            "error": "not found",
            "endpoints": ["/health", "/ready", "/metrics"],
        })

    # ── helpers ───────────────────────────────────────────────────────────

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self._send_text(status, body, content_type="application/json")

    def _send_text(self, status: int, body: str | bytes, content_type: str) -> None:
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


# ── public API ────────────────────────────────────────────────────────────────

def start_health_server(
    port: int = DEFAULT_PORT,
    *,
    host: str = "0.0.0.0",
    daemon: bool = True,
) -> threading.Thread:
    """
    Start the health-check server in a background thread.

    Args:
        port:   TCP port to bind (default: ``HERMES_HEALTH_PORT`` env var or 9090).
        host:   Bind address (default ``"0.0.0.0"``).
        daemon: Whether the thread is a daemon (exits when main process exits).

    Returns:
        The running ``threading.Thread`` (already started).
    """
    server = http.server.HTTPServer((host, port), _HealthHandler)

    def _serve() -> None:
        logger.info("Health server listening on http://%s:%d", host, port)
        try:
            server.serve_forever()
        except Exception as exc:
            logger.error("Health server error: %s", exc)

    thread = threading.Thread(target=_serve, name="hermes-health-server", daemon=daemon)
    thread.start()
    return thread


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Hermes Agent health-check server")
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting Hermes health server on %s:%d", args.host, args.port)

    # Run in the foreground when invoked as a script
    server = http.server.HTTPServer((args.host, args.port), _HealthHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Health server stopped.")


if __name__ == "__main__":
    main()
