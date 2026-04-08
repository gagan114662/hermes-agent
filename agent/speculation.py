"""
Prompt Speculation: proactively run read-only tools as soon as a message arrives.

When a message hits the gateway, a Speculator immediately starts running
safe read-only tools (memory, CRM, prospect lookup) in the background.
When the main agent begins, speculation results are injected as pre-loaded
context — saving 1-3 tool-call round-trips.

Safe tools (read-only, no side effects):
- memory (read mode)
- crm_find
- prospect_list
- session_search

Ported from CC's PromptSuggestion/speculation.ts pattern.
"""
from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Read-only tools safe to speculate with
SPECULATIVE_TOOLS = frozenset(['memory', 'crm_find', 'prospect_list', 'session_search'])

# Max time to wait for speculation results before proceeding
DEFAULT_SPECULATION_TIMEOUT = 3.0  # seconds

@dataclass
class SpeculationResult:
    tool_name: str
    args: dict[str, Any]
    result: str
    duration_ms: int
    error: str = ""


class Speculator:
    """Runs read-only tools proactively when a message arrives.

    Usage:
        speculator = Speculator()

        # When message arrives (in gateway):
        speculator.speculate_async(message_text, tool_executor)

        # Before first LLM call (in run_agent.py):
        context = speculator.get_context_injection(timeout=1.0)
        if context:
            prepend context to system prompt
    """

    def __init__(self):
        self._results: list[SpeculationResult] = []
        self._lock = threading.Lock()
        self._done_event = threading.Event()
        self._started = False

    def speculate_async(self, message: str, tool_executor: Any = None) -> None:
        """Fire-and-forget: run read-only tools on the incoming message."""
        if self._started:
            return  # Only speculate once per message
        self._started = True
        self._done_event.clear()

        threading.Thread(
            target=self._run_speculation,
            args=(message, tool_executor),
            daemon=True,
            name="speculator",
        ).start()
        logger.debug("[speculation] Started for message: %.60s...", message)

    def get_context_injection(self, timeout: float = DEFAULT_SPECULATION_TIMEOUT) -> str:
        """Wait up to `timeout` seconds for results, return formatted context string.

        Returns empty string if no useful results found.
        """
        self._done_event.wait(timeout=timeout)

        with self._lock:
            results = list(self._results)

        if not results:
            return ""

        return self._format_results(results)

    def reset(self) -> None:
        """Reset for next message. Call after each conversation turn."""
        with self._lock:
            self._results.clear()
        self._done_event.clear()
        self._started = False

    def _run_speculation(self, message: str, tool_executor: Any) -> None:
        """Worker: runs speculative tools. Handles errors gracefully."""
        try:
            self._speculate(message, tool_executor)
        except Exception as e:
            logger.debug("[speculation] Worker error: %s", e)
        finally:
            self._done_event.set()

    def _speculate(self, message: str, tool_executor: Any) -> None:
        """Core speculation logic: decide which tools to run and run them."""
        tasks = self._plan_speculation(message)
        if not tasks:
            logger.debug("[speculation] No tasks planned for message")
            return

        # Run tasks in parallel with individual error handling
        threads = []
        for tool_name, args in tasks:
            t = threading.Thread(
                target=self._run_tool,
                args=(tool_name, args, tool_executor),
                daemon=True,
            )
            threads.append(t)
            t.start()

        # Wait for all with 2.5s timeout
        for t in threads:
            t.join(timeout=2.5)

        logger.debug("[speculation] Completed %d tool calls", len(self._results))

    def _plan_speculation(self, message: str) -> list[tuple[str, dict]]:
        """Decide which read-only tools to run based on message content."""
        tasks = []
        msg_lower = message.lower()

        # Always read memory file directly (no agent context needed)
        tasks.append(('memory_read', {'query': message[:200]}))

        # CRM lookup if message mentions people/companies
        people_signals = ['customer', 'client', 'contact', 'company', 'prospect',
                         'email', 'phone', 'meeting', 'deal', 'sale']
        if any(s in msg_lower for s in people_signals):
            tasks.append(('crm_find_fn', {'query': message[:100]}))

        # Prospect list if researching/outreach
        prospect_signals = ['prospect', 'lead', 'outreach', 'research', 'reddit',
                           'linkedin', 'potential', 'target']
        if any(s in msg_lower for s in prospect_signals):
            tasks.append(('prospect_list_fn', {'limit': 5}))

        return tasks

    def _run_tool(self, tool_name: str, args: dict, tool_executor: Any) -> None:
        """Run a single speculative tool call."""
        start = time.monotonic()
        try:
            if tool_executor is None:
                # Fallback: try direct import
                result = self._call_tool_direct(tool_name, args)
            else:
                result = tool_executor.invoke_tool(tool_name, args, effective_task_id="speculation")

            duration_ms = int((time.monotonic() - start) * 1000)

            with self._lock:
                self._results.append(SpeculationResult(
                    tool_name=tool_name,
                    args=args,
                    result=str(result)[:1000],  # Cap result size
                    duration_ms=duration_ms,
                ))
            logger.debug("[speculation] %s completed in %dms", tool_name, duration_ms)

        except Exception as e:
            logger.debug("[speculation] Tool %s failed: %s", tool_name, e)

    def _call_tool_direct(self, tool_name: str, args: dict) -> str:
        """Direct tool call without executor (fallback)."""
        if tool_name == 'memory_read':
            # Read memory files directly — no agent context needed
            try:
                from hermes_constants import get_hermes_home
                import os
                hermes_home = get_hermes_home()
                parts = []
                for fname in ('memories/MEMORY.md', 'memories/USER.md', 'SOUL.md'):
                    fpath = os.path.join(hermes_home, fname)
                    if os.path.exists(fpath):
                        parts.append(open(fpath).read()[:800])
                if parts:
                    return '\n---\n'.join(parts)[:2000]
                return "No memory files found."
            except Exception as e:
                return f"Memory read failed: {e}"
        elif tool_name == 'crm_find_fn':
            from tools.crm_tool import crm_find_fn
            return crm_find_fn(**args)
        elif tool_name == 'prospect_list_fn':
            from tools.prospect_tool import prospect_list_fn
            return prospect_list_fn(**args)
        raise ValueError(f"Unknown speculative tool: {tool_name}")

    def _format_results(self, results: list[SpeculationResult]) -> str:
        """Format speculation results as context string for prepending to system prompt."""
        if not results:
            return ""

        lines = ["[PROACTIVE CONTEXT — pre-loaded before your response]"]
        for r in results:
            if r.error:
                continue
            result_preview = r.result[:300] if len(r.result) > 300 else r.result
            lines.append(f"\n{r.tool_name} result ({r.duration_ms}ms):\n{result_preview}")

        if len(lines) <= 1:
            return ""

        lines.append("\n[Use this context in your response if relevant. It was fetched proactively.]")
        return '\n'.join(lines)


# Module-level singleton — one speculator per gateway session
_speculator: Speculator | None = None
_spec_lock = threading.Lock()

def get_speculator() -> Speculator:
    """Get or create the module-level speculator singleton."""
    global _speculator
    with _spec_lock:
        if _speculator is None:
            _speculator = Speculator()
        return _speculator

def reset_speculator() -> None:
    """Reset speculation state for next message."""
    with _spec_lock:
        if _speculator:
            _speculator.reset()
