"""Agent Harness — multi-session orchestration layer for Hermes.

Exports the primary public surface:
  - HarnessConfig       — spec + limits for a harness run
  - ContextManager      — read/write progress.md + features.json
  - SessionOrchestrator — the main while-loop engine
  - Employee            — persistent goal-driven agent persona
"""
# HarnessConfig is imported eagerly — config.py has no heavy dependencies
# and eager import lets isinstance() checks and pickling work without trigger.
from harness.config import HarnessConfig

def __getattr__(name: str) -> type:
    if name == "ContextManager":
        from harness.context_manager import ContextManager
        return ContextManager
    if name == "SessionOrchestrator":
        from harness.session_orchestrator import SessionOrchestrator
        return SessionOrchestrator
    if name == "Employee":
        from harness.employee import Employee
        return Employee
    raise AttributeError(f"module 'harness' has no attribute {name!r}")

__all__ = ["HarnessConfig", "ContextManager", "SessionOrchestrator", "Employee"]
