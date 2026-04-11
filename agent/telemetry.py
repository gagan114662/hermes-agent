# agent/telemetry.py
"""
OpenTelemetry setup for Hermes Agent.

Sends traces to Honeycomb (or any OTLP-compatible backend).

Configuration (in ~/.hermes/config.yaml):

    telemetry:
      enabled: true
      exporter: honeycomb          # honeycomb | otlp | none
      honeycomb_api_key: "..."     # or set HONEYCOMB_API_KEY env var
      honeycomb_dataset: hermes-agent
      otlp_endpoint: "https://api.honeycomb.io"   # override for self-hosted

Environment variables (override config.yaml):
    HONEYCOMB_API_KEY
    OTEL_EXPORTER_OTLP_ENDPOINT
    OTEL_SERVICE_NAME
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Sentinel — set to True once configure_tracing() has been called
_configured = False

# Module-level tracer; callers import get_tracer() to get one.
_tracer = None


def get_tracer(name: str = "hermes"):
    """Return the shared tracer.  Safe to call before configure_tracing()."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


def configure_tracing(
    *,
    api_key: Optional[str] = None,
    dataset: str = "hermes-agent",
    endpoint: str = "https://api.honeycomb.io",
    service_name: str = "hermes-agent",
    enabled: bool = True,
) -> bool:
    """
    Set up a global TracerProvider that exports to Honeycomb via OTLP/HTTP.

    Returns True if telemetry was successfully initialised, False otherwise.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _configured

    if _configured:
        return True

    if not enabled:
        logger.debug("Telemetry disabled by configuration")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError:
        logger.info(
            "opentelemetry packages not installed — tracing disabled. "
            "Install with: pip install 'hermes-agent[otel]'"
        )
        return False

    resolved_key = api_key or os.environ.get("HONEYCOMB_API_KEY", "")
    resolved_endpoint = (
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint).rstrip("/")
        + "/v1/traces"
    )
    resolved_service = os.environ.get("OTEL_SERVICE_NAME", service_name)

    headers = {}
    if resolved_key:
        headers["x-honeycomb-team"] = resolved_key
    if dataset:
        headers["x-honeycomb-dataset"] = dataset

    resource = Resource.create({SERVICE_NAME: resolved_service})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint=resolved_endpoint,
        headers=headers,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _configured = True

    logger.info(
        "Telemetry configured: endpoint=%s service=%s dataset=%s",
        resolved_endpoint,
        resolved_service,
        dataset,
    )
    return True


def configure_from_config() -> bool:
    """
    Read telemetry settings from ~/.hermes/config.yaml and call configure_tracing().
    Called once at gateway / agent startup.
    """
    try:
        from hermes_constants import get_hermes_home
        import yaml
        cfg_path = get_hermes_home() / "config.yaml"
        if not cfg_path.exists():
            return False
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        t = cfg.get("telemetry") or {}
        if not t.get("enabled", False):
            return False
        return configure_tracing(
            api_key=t.get("honeycomb_api_key") or os.environ.get("HONEYCOMB_API_KEY", ""),
            dataset=t.get("honeycomb_dataset", "hermes-agent"),
            endpoint=t.get("otlp_endpoint", "https://api.honeycomb.io"),
            service_name=t.get("service_name", "hermes-agent"),
            enabled=True,
        )
    except Exception as e:
        logger.debug("Could not configure telemetry from config.yaml: %s", e)
        return False


# ---------------------------------------------------------------------------
# Context manager helpers so call sites stay readable
# ---------------------------------------------------------------------------

class _NoopSpan:
    """Returned when OTel is not installed — all operations are no-ops."""
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def set_attribute(self, *a, **kw): pass
    def record_exception(self, *a, **kw): pass
    def set_status(self, *a, **kw): pass
    def add_event(self, *a, **kw): pass


class _NoopTracer:
    def start_as_current_span(self, name, **kw):
        return _NoopSpan()
    def start_span(self, name, **kw):
        return _NoopSpan()


def span(name: str, **attributes):
    """
    Context manager that opens a span on the global tracer.

    Usage::

        with telemetry.span("gateway.run_agent", session_id=sid) as s:
            ...
            s.set_attribute("response_length", len(result))
    """
    tracer = get_tracer("hermes")
    ctx = tracer.start_as_current_span(name)
    _span = ctx.__enter__()
    # Attach initial attributes
    for k, v in attributes.items():
        try:
            _span.set_attribute(k, v)
        except Exception:
            pass

    class _ManagedSpan:
        def __enter__(self):
            return _span

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is not None:
                try:
                    from opentelemetry.trace import StatusCode
                    _span.record_exception(exc_val)
                    _span.set_status(StatusCode.ERROR, str(exc_val))
                except Exception:
                    pass
            ctx.__exit__(exc_type, exc_val, exc_tb)
            return False  # don't suppress exceptions

    return _ManagedSpan()
