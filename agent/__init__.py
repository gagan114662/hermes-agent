"""Agent internals -- extracted modules from run_agent.py.

These modules contain pure utility functions and self-contained classes
that were previously embedded in the 3,600-line run_agent.py. Extracting
them makes run_agent.py focused on the AIAgent orchestrator class.
"""

# Auto-load Sentry tracing hooks when SENTRY_DSN is present.
# The module is safe to import even when sentry-sdk is not installed.
try:
    import agent.sentry_tracing  # noqa: F401  registers hooks as side-effect
except Exception:
    pass
