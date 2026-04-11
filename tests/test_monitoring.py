"""
Tests for the monitoring stack:
  - tools/metrics.py       (MetricsCollector)
  - hermes_cli/log_config.py  (configure_logging, bind_log_context)
  - hermes_cli/sentry.py   (init_sentry, capture_exception, etc.)
  - scripts/health_server.py  (HTTP handler, start_health_server)
  - tools/registry.py      (dispatch auto-records metrics)
"""

from __future__ import annotations

import io
import json
import logging
import threading
import time
import urllib.request
from unittest.mock import MagicMock, patch

import pytest


# ─── MetricsCollector ────────────────────────────────────────────────────────

class TestMetricsCollector:
    @pytest.fixture()
    def mc(self):
        from tools.metrics import MetricsCollector
        return MetricsCollector()

    def test_initial_snapshot_is_empty(self, mc):
        snap = mc.snapshot()
        assert snap["total_calls"] == 0
        assert snap["total_errors"] == 0
        assert snap["error_rate"] == 0.0
        assert snap["tools"] == {}

    def test_record_increments_calls(self, mc):
        mc.record("terminal", 50.0)
        assert mc.snapshot()["total_calls"] == 1
        assert mc.snapshot()["tools"]["terminal"]["calls"] == 1

    def test_record_error_increments_errors(self, mc):
        mc.record("terminal", 50.0, success=False)
        snap = mc.snapshot()
        assert snap["total_errors"] == 1
        assert snap["tools"]["terminal"]["errors"] == 1

    def test_error_rate_calculation(self, mc):
        mc.record("terminal", 10.0, success=True)
        mc.record("terminal", 10.0, success=False)
        snap = mc.snapshot()
        assert snap["tools"]["terminal"]["error_rate"] == 0.5
        assert snap["error_rate"] == 0.5

    def test_multiple_tools_tracked_independently(self, mc):
        mc.record("terminal", 10.0)
        mc.record("read_file", 5.0)
        mc.record("read_file", 8.0)
        snap = mc.snapshot()
        assert snap["tools"]["terminal"]["calls"] == 1
        assert snap["tools"]["read_file"]["calls"] == 2

    def test_duration_percentiles_computed(self, mc):
        for ms in range(1, 101):   # 1..100 ms uniform distribution
            mc.record("web_search", float(ms))
        stats = mc.snapshot()["tools"]["web_search"]
        # Tight range assertions — not just upper bounds
        assert 45.0 < stats["p50_ms"] < 55.0, f"p50={stats['p50_ms']} not in [45,55]"
        assert 90.0 < stats["p95_ms"] <= 99.0, f"p95={stats['p95_ms']} not in (90,99]"
        assert 95.0 < stats["p99_ms"] <= 100.0, f"p99={stats['p99_ms']} not in (95,100]"
        assert stats["mean_ms"] > 0

    def test_mean_ms_exact_for_uniform_100(self, mc):
        """Mean of 1..100 must be exactly 50.5."""
        for ms in range(1, 101):
            mc.record("exact_mean_tool", float(ms))
        stats = mc.snapshot()["tools"]["exact_mean_tool"]
        assert abs(stats["mean_ms"] - 50.5) < 0.01, f"mean={stats['mean_ms']} expected 50.5"

    def test_error_rate_when_zero_calls(self, mc):
        """error_rate with 0 total_calls must be 0.0 — no division by zero."""
        snap = mc.snapshot()
        assert snap["error_rate"] == 0.0
        assert snap["total_calls"] == 0

    def test_mean_ms_correct(self, mc):
        mc.record("tool", 10.0)
        mc.record("tool", 20.0)
        mc.record("tool", 30.0)
        snap = mc.snapshot()
        assert snap["tools"]["tool"]["mean_ms"] == pytest.approx(20.0, abs=0.1)

    def test_thread_safe_concurrent_writes(self, mc):
        errors: list[Exception] = []

        def _write():
            try:
                for _ in range(50):
                    mc.record("concurrent_tool", 1.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_write) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert mc.snapshot()["total_calls"] == 500

    def test_reset_clears_all_data(self, mc):
        mc.record("tool", 10.0)
        mc.reset()
        snap = mc.snapshot()
        assert snap["total_calls"] == 0
        assert snap["tools"] == {}

    def test_uptime_increases_over_time(self, mc):
        snap1 = mc.snapshot()
        time.sleep(0.05)
        snap2 = mc.snapshot()
        assert snap2["uptime_s"] >= snap1["uptime_s"]

    def test_ring_buffer_does_not_grow_unbounded(self, mc):
        """Recording >1000 samples should not cause memory to grow unbounded.

        We verify this via the public API: p99 must remain computable and
        not regress after many more samples than the ring buffer limit.
        """
        # Record more than _MAX_SAMPLES (1000)
        for i in range(1100):
            mc.record("noisy_tool", float(i % 100))
        # Public API must still work and p99 must be sane
        stats = mc.snapshot()["tools"]["noisy_tool"]
        assert stats["calls"] == 1100
        assert 0.0 < stats["p99_ms"] <= 100.0

    def test_zero_calls_no_division_error(self, mc):
        snap = mc.snapshot()
        assert snap["error_rate"] == 0.0


class TestMetricsPrometheus:
    @pytest.fixture()
    def mc(self):
        from tools.metrics import MetricsCollector
        m = MetricsCollector()
        m.record("terminal", 42.0)
        m.record("read_file", 10.0, success=False)
        return m

    def test_output_is_string(self, mc):
        assert isinstance(mc.prometheus(), str)

    def test_contains_tool_calls_metric(self, mc):
        text = mc.prometheus()
        assert "hermes_tool_calls_total" in text

    def test_contains_tool_errors_metric(self, mc):
        text = mc.prometheus()
        assert "hermes_tool_errors_total" in text

    def test_contains_p50_metric(self, mc):
        text = mc.prometheus()
        assert "hermes_tool_duration_p50_ms" in text

    def test_contains_p95_metric(self, mc):
        text = mc.prometheus()
        assert "hermes_tool_duration_p95_ms" in text

    def test_label_format(self, mc):
        text = mc.prometheus()
        assert 'tool="terminal"' in text

    def test_uptime_metric_present(self, mc):
        text = mc.prometheus()
        assert "hermes_uptime_seconds" in text

    def test_error_count_reflects_record(self, mc):
        lines = mc.prometheus().splitlines()
        error_lines = [l for l in lines if "hermes_tool_errors_total" in l and 'tool="read_file"' in l]
        assert error_lines
        # Value should be 1
        assert error_lines[0].endswith(" 1")


# ─── registry.dispatch → metrics integration ─────────────────────────────────

class TestRegistryMetricsIntegration:
    def test_successful_dispatch_records_call(self):
        from tools.registry import ToolRegistry
        from tools.metrics import MetricsCollector

        reg = ToolRegistry()
        mc = MetricsCollector()

        reg.register(
            name="test_ping",
            toolset="test",
            schema={"name": "test_ping", "description": "ping", "parameters": {"type": "object", "properties": {}, "required": []}},
            handler=lambda args, **kw: json.dumps({"ok": True}),
        )

        with patch("tools.registry._get_metrics", return_value=mc):
            reg.dispatch("test_ping", {})

        snap = mc.snapshot()
        assert snap["total_calls"] == 1
        assert snap["tools"]["test_ping"]["calls"] == 1
        assert snap["tools"]["test_ping"]["errors"] == 0

    def test_error_response_recorded_as_failure(self):
        from tools.registry import ToolRegistry
        from tools.metrics import MetricsCollector

        reg = ToolRegistry()
        mc = MetricsCollector()

        reg.register(
            name="test_fail",
            toolset="test",
            schema={"name": "test_fail", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
            handler=lambda args, **kw: json.dumps({"error": "something broke"}),
        )

        with patch("tools.registry._get_metrics", return_value=mc):
            reg.dispatch("test_fail", {})

        snap = mc.snapshot()
        assert snap["tools"]["test_fail"]["errors"] == 1

    def test_exception_recorded_as_failure(self):
        from tools.registry import ToolRegistry
        from tools.metrics import MetricsCollector

        reg = ToolRegistry()
        mc = MetricsCollector()

        reg.register(
            name="test_exc",
            toolset="test",
            schema={"name": "test_exc", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
            handler=lambda args, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        with patch("tools.registry._get_metrics", return_value=mc):
            result = reg.dispatch("test_exc", {})

        assert "error" in json.loads(result)
        snap = mc.snapshot()
        assert snap["tools"]["test_exc"]["errors"] == 1

    def test_duration_recorded(self):
        from tools.registry import ToolRegistry
        from tools.metrics import MetricsCollector

        reg = ToolRegistry()
        mc = MetricsCollector()

        def _slow(args, **kw):
            time.sleep(0.02)
            return json.dumps({"ok": True})

        reg.register(
            name="test_slow",
            toolset="test",
            schema={"name": "test_slow", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}},
            handler=_slow,
        )

        with patch("tools.registry._get_metrics", return_value=mc):
            reg.dispatch("test_slow", {})

        stats = mc.snapshot()["tools"]["test_slow"]
        assert stats["mean_ms"] >= 15.0  # at least 15 ms


# ─── log_config ──────────────────────────────────────────────────────────────

class TestLogConfig:
    def test_configure_logging_does_not_raise(self):
        from hermes_cli.log_config import configure_logging
        configure_logging(level="INFO", json_logs=False)
        configure_logging(level="DEBUG", json_logs=False)

    def test_configure_logging_sets_root_level(self):
        from hermes_cli.log_config import configure_logging
        configure_logging(level="WARNING", json_logs=False)
        assert logging.getLogger().level == logging.WARNING

    def test_configure_logging_json_mode(self):
        from hermes_cli.log_config import configure_logging
        configure_logging(level="INFO", json_logs=True)
        root = logging.getLogger()
        assert any(hasattr(h, "formatter") for h in root.handlers)

    def test_configure_logging_is_idempotent(self):
        from hermes_cli.log_config import configure_logging
        configure_logging(level="INFO", json_logs=False)
        handler_count_1 = len(logging.getLogger().handlers)
        configure_logging(level="INFO", json_logs=False)
        handler_count_2 = len(logging.getLogger().handlers)
        assert handler_count_1 == handler_count_2

    def test_bind_log_context_stores_fields(self):
        from hermes_cli.log_config import bind_log_context, get_log_context, clear_log_context
        clear_log_context()
        bind_log_context(session_id="abc123", profile="coder")
        ctx = get_log_context()
        assert ctx["session_id"] == "abc123"
        assert ctx["profile"] == "coder"
        clear_log_context()

    def test_clear_log_context_removes_fields(self):
        from hermes_cli.log_config import bind_log_context, get_log_context, clear_log_context
        bind_log_context(session_id="xyz")
        clear_log_context()
        assert get_log_context() == {}

    def test_bind_accumulates_across_calls(self):
        from hermes_cli.log_config import bind_log_context, get_log_context, clear_log_context
        clear_log_context()
        bind_log_context(a=1)
        bind_log_context(b=2)
        ctx = get_log_context()
        assert ctx["a"] == 1
        assert ctx["b"] == 2
        clear_log_context()

    def test_context_filter_injects_fields(self):
        from hermes_cli.log_config import _ContextFilter, bind_log_context, clear_log_context
        clear_log_context()
        bind_log_context(request_id="req-42")

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        f = _ContextFilter()
        f.filter(record)
        assert getattr(record, "request_id", None) == "req-42"
        clear_log_context()

    def test_json_formatter_produces_valid_json(self):
        from hermes_cli.log_config import configure_logging, _make_json_formatter, _JSON_LOGGER_AVAILABLE
        configure_logging(level="DEBUG", json_logs=True)

        formatter = _make_json_formatter()
        record = logging.LogRecord(
            name="hermes.test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        if _JSON_LOGGER_AVAILABLE:
            parsed = json.loads(output)
            assert "message" in parsed or "msg" in parsed or "test message" in output
        else:
            # Fallback text formatter — just verify the message appears
            assert "test message" in output


# ─── sentry.py ───────────────────────────────────────────────────────────────

class TestSentry:
    def setup_method(self):
        """Reset sentry state between tests."""
        import hermes_cli.sentry as sentry_mod
        sentry_mod._initialized = False

    def test_init_sentry_noop_without_dsn(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        from hermes_cli.sentry import init_sentry, is_configured
        result = init_sentry()
        assert result is False
        assert not is_configured()

    def test_capture_exception_noop_when_not_initialized(self):
        from hermes_cli.sentry import capture_exception
        result = capture_exception(ValueError("test"))
        assert result is None

    def test_capture_message_noop_when_not_initialized(self):
        from hermes_cli.sentry import capture_message
        result = capture_message("hello")
        assert result is None

    def test_add_breadcrumb_noop_when_not_initialized(self):
        from hermes_cli.sentry import add_breadcrumb
        add_breadcrumb("something happened")  # must not raise

    def test_set_user_noop_when_not_initialized(self):
        from hermes_cli.sentry import set_user
        set_user("user123")  # must not raise

    def test_is_configured_returns_false_initially(self):
        from hermes_cli.sentry import is_configured
        assert not is_configured()

    def test_init_sentry_with_dsn_calls_sdk(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        import hermes_cli.sentry as sentry_mod

        mock_init = MagicMock()
        mock_integration = MagicMock()

        with patch.object(sentry_mod, "_sdk_available", True), \
             patch.object(sentry_mod, "sentry_sdk", create=True) as mock_sdk, \
             patch.object(sentry_mod, "LoggingIntegration", return_value=mock_integration, create=True):
            mock_sdk.init = mock_init
            result = sentry_mod.init_sentry(dsn="https://fake@sentry.io/123")

        assert result is True
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args[1]
        assert call_kwargs["dsn"] == "https://fake@sentry.io/123"

    def test_init_sentry_warns_when_sdk_missing(self, monkeypatch, caplog):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        import hermes_cli.sentry as sentry_mod
        with patch.object(sentry_mod, "_sdk_available", False):
            with caplog.at_level(logging.WARNING, logger="hermes_cli.sentry"):
                result = sentry_mod.init_sentry(dsn="https://fake@sentry.io/1")
        assert result is False
        assert "sentry-sdk" in caplog.text or "not installed" in caplog.text


# ─── health_server.py ────────────────────────────────────────────────────────

class TestHealthHandler:
    """Test the HTTP handler logic without starting a real server."""

    def _call_handler(self, path: str) -> tuple[int, dict | str]:
        """Invoke the handler's GET method and return (status_code, body)."""
        from scripts.health_server import _HealthHandler

        # Build a fake request handler
        captured: dict = {}

        class _FakeSocket:
            def makefile(self, *a, **kw):
                return io.BytesIO(b"")

        handler = _HealthHandler.__new__(_HealthHandler)
        handler.path = path
        handler.wfile = io.BytesIO()
        handler.server = MagicMock()

        status_sent: list[int] = []
        headers_sent: list[tuple] = []

        def fake_send_response(code):
            status_sent.append(code)

        def fake_send_header(name, value):
            headers_sent.append((name, value))

        def fake_end_headers():
            pass

        def fake_log(fmt, *args):
            pass

        handler.send_response = fake_send_response
        handler.send_header = fake_send_header
        handler.end_headers = fake_end_headers
        handler.log_message = fake_log

        handler.do_GET()

        body_bytes = handler.wfile.getvalue()
        status = status_sent[0] if status_sent else 0
        # Detect content type from headers
        ct = dict(headers_sent).get("Content-Type", "")
        if "json" in ct:
            try:
                return status, json.loads(body_bytes.decode())
            except Exception:
                pass
        return status, body_bytes.decode()

    def test_health_returns_200(self):
        status, body = self._call_handler("/health")
        assert status == 200

    def test_health_body_has_status_ok(self):
        _, body = self._call_handler("/health")
        assert isinstance(body, dict)
        assert body["status"] == "ok"

    def test_health_body_has_version(self):
        _, body = self._call_handler("/health")
        assert "version" in body

    def test_health_body_has_metrics(self):
        _, body = self._call_handler("/health")
        assert "metrics" in body

    def test_ready_returns_200_when_healthy(self):
        from tools.metrics import METRICS
        METRICS.reset()
        status, _ = self._call_handler("/ready")
        assert status == 200

    def test_metrics_returns_200(self):
        status, _ = self._call_handler("/metrics")
        assert status == 200

    def test_metrics_body_contains_prometheus_text(self):
        from tools.metrics import METRICS
        METRICS.record("test_tool", 10.0)
        _, body = self._call_handler("/metrics")
        assert "hermes_" in body

    def test_unknown_path_returns_404(self):
        status, body = self._call_handler("/nonexistent")
        assert status == 404
        assert isinstance(body, dict)
        assert "endpoints" in body

    def test_path_with_trailing_slash(self):
        status, _ = self._call_handler("/health/")
        assert status == 200

    def test_ready_503_when_high_error_rate(self):
        from tools.metrics import MetricsCollector
        from scripts.health_server import _HealthHandler

        mc = MetricsCollector()
        for _ in range(20):
            mc.record("bad_tool", 10.0, success=False)  # 100% error rate

        with patch("scripts.health_server._metrics_snapshot", return_value=mc.snapshot()):
            status, body = self._call_handler("/ready")
        assert status == 503
        assert body["status"] == "degraded"


class TestStartHealthServer:
    def test_server_starts_and_responds(self):
        """Spin up a real server on an OS-assigned port and hit /health."""
        from scripts.health_server import start_health_server

        # Port 0 → OS picks a free port
        import http.server
        server = http.server.HTTPServer(("127.0.0.1", 0), MagicMock())
        port = server.server_address[1]
        server.server_close()

        # Use a well-known free port by getting one first
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        thread = start_health_server(port=port, host="127.0.0.1")
        time.sleep(0.2)  # give server time to bind

        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as resp:
                body = json.loads(resp.read())
            assert body["status"] == "ok"
        finally:
            # Thread is daemon — it dies with the test process
            pass

    def test_server_thread_is_daemon(self):
        from scripts.health_server import start_health_server
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        thread = start_health_server(port=port, host="127.0.0.1", daemon=True)
        assert thread.daemon is True
