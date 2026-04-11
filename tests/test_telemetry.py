# tests/test_telemetry.py
"""Unit tests for agent/telemetry.py — no OTel packages required."""

import importlib
import sys
import types
import pytest


def _reload_telemetry():
    """Return a fresh copy of the telemetry module with _configured reset."""
    if "agent.telemetry" in sys.modules:
        del sys.modules["agent.telemetry"]
    import agent.telemetry as t
    return t


# ---------------------------------------------------------------------------
# Noop path — opentelemetry not installed
# ---------------------------------------------------------------------------

class TestNoopWhenPackageMissing:
    def test_get_tracer_returns_noop(self, monkeypatch):
        t = _reload_telemetry()
        # Make opentelemetry unimportable
        monkeypatch.setitem(sys.modules, "opentelemetry", None)
        tracer = t.get_tracer("hermes")
        # Should be the noop tracer
        assert hasattr(tracer, "start_as_current_span")

    def test_configure_tracing_returns_false_on_import_error(self, monkeypatch):
        t = _reload_telemetry()
        monkeypatch.setitem(sys.modules, "opentelemetry", None)
        monkeypatch.setitem(sys.modules, "opentelemetry.sdk", None)
        result = t.configure_tracing(api_key="key", enabled=True)
        assert result is False

    def test_span_context_manager_noop(self):
        t = _reload_telemetry()
        # span() must work even when OTel is missing
        raised = False
        try:
            with t.span("test.noop") as s:
                s.set_attribute("k", "v")
        except Exception:
            raised = True
        assert not raised


# ---------------------------------------------------------------------------
# configure_tracing disabled path
# ---------------------------------------------------------------------------

class TestDisabled:
    def test_configure_tracing_disabled(self):
        t = _reload_telemetry()
        result = t.configure_tracing(enabled=False)
        assert result is False
        assert t._configured is False


# ---------------------------------------------------------------------------
# configure_from_config — missing config.yaml
# ---------------------------------------------------------------------------

class TestConfigureFromConfig:
    def test_returns_false_when_no_config_yaml(self, tmp_path, monkeypatch):
        t = _reload_telemetry()

        def _fake_get_hermes_home():
            return tmp_path

        monkeypatch.setattr(
            "hermes_constants.get_hermes_home",
            _fake_get_hermes_home,
            raising=False,
        )
        result = t.configure_from_config()
        assert result is False

    def test_returns_false_when_telemetry_disabled_in_config(self, tmp_path, monkeypatch):
        t = _reload_telemetry()
        cfg = tmp_path / "config.yaml"
        cfg.write_text("telemetry:\n  enabled: false\n", encoding="utf-8")

        monkeypatch.setattr(
            "hermes_constants.get_hermes_home",
            lambda: tmp_path,
            raising=False,
        )
        result = t.configure_from_config()
        assert result is False


# ---------------------------------------------------------------------------
# _NoopSpan / _NoopTracer sanity
# ---------------------------------------------------------------------------

class TestNoopClasses:
    def test_noop_span_all_methods_safe(self):
        from agent.telemetry import _NoopSpan
        s = _NoopSpan()
        with s:
            s.set_attribute("a", 1)
            s.record_exception(ValueError("x"))
            s.set_status("ok")
            s.add_event("evt")

    def test_noop_tracer_start_span(self):
        from agent.telemetry import _NoopTracer, _NoopSpan
        t = _NoopTracer()
        ctx = t.start_as_current_span("x")
        assert hasattr(ctx, "__enter__")
