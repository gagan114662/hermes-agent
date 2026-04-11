#!/usr/bin/env python3
"""
Delegate Tool -- Subagent Architecture

Spawns child AIAgent instances with isolated context, restricted toolsets,
and their own terminal sessions. Supports single-task and batch (parallel)
modes. The parent blocks until all children complete.

Each child gets:
  - A fresh conversation (no parent history)
  - Its own task_id (own terminal session, file ops cache)
  - A restricted toolset (configurable, with blocked tools always stripped)
  - A focused system prompt built from the delegated goal + context

The parent's context only sees the delegation call and the summary result,
never the child's intermediate tool calls or reasoning.
"""

import json
import logging
logger = logging.getLogger(__name__)
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional


# Tools that children must never have access to
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",   # no recursive delegation
    "clarify",         # no user interaction
    "memory",          # no writes to shared MEMORY.md
    "send_message",    # no cross-platform side effects
    "execute_code",    # children should reason step-by-step, not write scripts
])

_DEFAULT_MAX_CONCURRENT_CHILDREN = 3
MAX_DEPTH = 2  # parent (0) -> child (1) -> grandchild rejected (2)


def _get_max_concurrent_children() -> int:
    """Read delegation.max_concurrent_children from config, falling back to
    DELEGATION_MAX_CONCURRENT_CHILDREN env var, then the default (3).

    Uses the same ``_load_config()`` path that the rest of ``delegate_task``
    uses, keeping config priority consistent (config.yaml > env > default).
    """
    cfg = _load_config()
    val = cfg.get("max_concurrent_children")
    if val is not None:
        try:
            return max(1, int(val))
        except (TypeError, ValueError):
            logger.warning(
                "delegation.max_concurrent_children=%r is not a valid integer; "
                "using default %d", val, _DEFAULT_MAX_CONCURRENT_CHILDREN,
            )
    env_val = os.getenv("DELEGATION_MAX_CONCURRENT_CHILDREN")
    if env_val:
        try:
            return max(1, int(env_val))
        except (TypeError, ValueError):
            pass
    return _DEFAULT_MAX_CONCURRENT_CHILDREN
DEFAULT_MAX_ITERATIONS = 50
_HEARTBEAT_INTERVAL = 30  # seconds between parent activity heartbeats during delegation
DEFAULT_TOOLSETS = ["terminal", "file", "web"]


def check_delegate_requirements() -> bool:
    """Delegation has no external requirements -- always available."""
    return True


def _build_child_system_prompt(goal: str, context: Optional[str] = None) -> str:
    """Build a focused system prompt for a child agent."""
    parts = [
        "You are a focused subagent working on a specific delegated task.",
        "",
        f"YOUR TASK:\n{goal}",
    ]
    if context and context.strip():
        parts.append(f"\nCONTEXT:\n{context}")
    parts.append(
        "\nComplete this task using the tools available to you. "
        "When finished, provide a clear, concise summary of:\n"
        "- What you did\n"
        "- What you found or accomplished\n"
        "- Any files you created or modified\n"
        "- Any issues encountered\n\n"
        "Be thorough but concise -- your response is returned to the "
        "parent agent as a summary."
    )
    return "\n".join(parts)


def _strip_blocked_tools(toolsets: List[str]) -> List[str]:
    """Remove toolsets that contain only blocked tools."""
    blocked_toolset_names = {
        "delegation", "clarify", "memory", "code_execution",
    }
    return [t for t in toolsets if t not in blocked_toolset_names]


def _build_child_progress_callback(task_index: int, parent_agent, task_count: int = 1) -> Optional[callable]:
    """Build a callback that relays child agent tool calls to the parent display.

    Two display paths:
      CLI:     prints tree-view lines above the parent's delegation spinner
      Gateway: batches tool names and relays to parent's progress callback

    Returns None if no display mechanism is available, in which case the
    child agent runs with no progress callback (identical to current behavior).
    """
    spinner = getattr(parent_agent, '_delegate_spinner', None)
    parent_cb = getattr(parent_agent, 'tool_progress_callback', None)

    if not spinner and not parent_cb:
        return None  # No display → no callback → zero behavior change

    # Show 1-indexed prefix only in batch mode (multiple tasks)
    prefix = f"[{task_index + 1}] " if task_count > 1 else ""

    # Gateway: batch tool names, flush periodically
    _BATCH_SIZE = 5
    _batch: List[str] = []

    def _callback(event_type: str, tool_name: str = None, preview: str = None, extra=None):
        # Normalise the calling convention.
        #
        # run_agent.py calls: callback("tool.started", name, preview, args)
        #                 or: callback("_thinking", text)
        # Legacy / batch callers may still call: callback(tool_name, preview)
        #   e.g. callback("web_search", "some preview")
        #        callback("web_search")
        #
        # We detect the event-style convention by checking known event prefixes.
        _EVENT_TYPES = ("tool.started", "tool.done", "_thinking", "subagent_progress")
        if event_type not in _EVENT_TYPES:
            # Backwards-compat: first arg is actually the tool name
            tool_name = event_type
            event_type = "tool.started"
            # preview is already in the right position

        # Special "_thinking" event: model produced text content (reasoning)
        if event_type == "_thinking":
            # thinking text is in tool_name (second positional arg)
            thinking_text = tool_name
            if spinner:
                short = (thinking_text[:55] + "...") if thinking_text and len(thinking_text) > 55 else (thinking_text or "")
                try:
                    spinner.print_above(f" {prefix}├─ 💭 \"{short}\"")
                except Exception as e:
                    logger.debug("Spinner print_above failed: %s", e)
            # Don't relay thinking to gateway (too noisy for chat)
            return

        # Regular tool call event
        if spinner:
            short = (preview[:35] + "...") if preview and len(preview) > 35 else (preview or "")
            from agent.display import get_tool_emoji
            emoji = get_tool_emoji(tool_name or "")
            line = f" {prefix}├─ {emoji} {tool_name}"
            if short:
                line += f"  \"{short}\""
            try:
                spinner.print_above(line)
            except Exception as e:
                logger.debug("Spinner print_above failed: %s", e)

        if parent_cb:
            _batch.append(tool_name or event_type)
            if len(_batch) >= _BATCH_SIZE:
                summary = ", ".join(_batch)
                try:
                    parent_cb("subagent_progress", f"🔀 {prefix}{summary}")
                except Exception as e:
                    logger.debug("Parent callback failed: %s", e)
                _batch.clear()

    def _flush():
        """Flush remaining batched tool names to gateway on completion."""
        if parent_cb and _batch:
            summary = ", ".join(_batch)
            try:
                parent_cb("subagent_progress", f"🔀 {prefix}{summary}")
            except Exception as e:
                logger.debug("Parent callback flush failed: %s", e)
            _batch.clear()

    _callback._flush = _flush
    return _callback


def _build_child_agent(
    task_index: int,
    goal: str,
    context: Optional[str],
    toolsets: Optional[List[str]],
    model: Optional[str],
    max_iterations: int,
    parent_agent,
    # Credential overrides from delegation config (provider:model resolution)
    override_provider: Optional[str] = None,
    override_base_url: Optional[str] = None,
    override_api_key: Optional[str] = None,
    override_api_mode: Optional[str] = None,
):
    """
    Build a child AIAgent on the main thread (thread-safe construction).
    Returns the constructed child agent without running it.

    When override_* params are set (from delegation config), the child uses
    those credentials instead of inheriting from the parent.  This enables
    routing subagents to a different provider:model pair (e.g. cheap/fast
    model on OpenRouter while the parent runs on Nous Portal).
    """
    from run_agent import AIAgent

    # When no explicit toolsets given, inherit from parent's enabled toolsets
    # so disabled tools (e.g. web) don't leak to subagents.
    parent_toolsets = set(getattr(parent_agent, "enabled_toolsets", None) or DEFAULT_TOOLSETS)
    if toolsets:
        # Intersect with parent — subagent must not gain tools the parent lacks
        child_toolsets = _strip_blocked_tools([t for t in toolsets if t in parent_toolsets])
    elif parent_agent and getattr(parent_agent, "enabled_toolsets", None):
        child_toolsets = _strip_blocked_tools(parent_agent.enabled_toolsets)
    else:
        child_toolsets = _strip_blocked_tools(DEFAULT_TOOLSETS)

    # ── Inject memdir session knowledge into child context ───────────────────
    # Automatically pass session discoveries to children so they don't
    # re-discover what sibling agents already found.
    try:
        from agent.memdir import inject_memdir_context
        session_id = getattr(parent_agent, "session_id", None) or "default"
        context = inject_memdir_context(session_id, context)
    except Exception as _memdir_exc:
        logger.debug("delegate_tool: memdir inject failed: %s", _memdir_exc)

    child_prompt = _build_child_system_prompt(goal, context)
    # Extract parent's API key so subagents inherit auth (e.g. Nous Portal).
    parent_api_key = getattr(parent_agent, "api_key", None)
    if (not parent_api_key) and hasattr(parent_agent, "_client_kwargs"):
        parent_api_key = parent_agent._client_kwargs.get("api_key")

    # Build progress callback to relay tool calls to parent display
    child_progress_cb = _build_child_progress_callback(task_index, parent_agent)

    # Each subagent gets its own iteration budget capped at max_iterations
    # (configurable via delegation.max_iterations, default 50).  This means
    # total iterations across parent + subagents can exceed the parent's
    # max_iterations.  The user controls the per-subagent cap in config.yaml.

    # Resolve effective credentials: config override > parent inherit
    effective_model = model or parent_agent.model
    effective_provider = override_provider or getattr(parent_agent, "provider", None)
    effective_base_url = override_base_url or parent_agent.base_url
    effective_api_key = override_api_key or parent_api_key
    effective_api_mode = override_api_mode or getattr(parent_agent, "api_mode", None)
    effective_acp_command = getattr(parent_agent, "acp_command", None)
    effective_acp_args = list(getattr(parent_agent, "acp_args", []) or [])

    # Resolve reasoning config: delegation override > parent inherit
    parent_reasoning = getattr(parent_agent, "reasoning_config", None)
    child_reasoning = parent_reasoning
    try:
        delegation_cfg = _load_config()
        delegation_effort = str(delegation_cfg.get("reasoning_effort") or "").strip()
        if delegation_effort:
            from hermes_constants import parse_reasoning_effort
            parsed = parse_reasoning_effort(delegation_effort)
            if parsed is not None:
                child_reasoning = parsed
            else:
                logger.warning(
                    "Unknown delegation.reasoning_effort '%s', inheriting parent level",
                    delegation_effort,
                )
    except Exception as exc:
        logger.debug("Could not load delegation reasoning_effort: %s", exc)

    child = AIAgent(
        base_url=effective_base_url,
        api_key=effective_api_key,
        model=effective_model,
        provider=effective_provider,
        api_mode=effective_api_mode,
        acp_command=effective_acp_command,
        acp_args=effective_acp_args,
        max_iterations=max_iterations,
        max_tokens=getattr(parent_agent, "max_tokens", None),
        reasoning_config=child_reasoning,
        prefill_messages=getattr(parent_agent, "prefill_messages", None),
        enabled_toolsets=child_toolsets,
        quiet_mode=True,
        ephemeral_system_prompt=child_prompt,
        log_prefix=f"[subagent-{task_index}]",
        platform=parent_agent.platform,
        skip_context_files=True,
        skip_memory=True,
        clarify_callback=None,
        session_db=getattr(parent_agent, '_session_db', None),
        providers_allowed=parent_agent.providers_allowed,
        providers_ignored=parent_agent.providers_ignored,
        providers_order=parent_agent.providers_order,
        provider_sort=parent_agent.provider_sort,
        tool_progress_callback=child_progress_cb,
        iteration_budget=None,  # fresh budget per subagent
    )
    # Inherit print function from parent
    if hasattr(parent_agent, '_print_fn'):
        child._print_fn = parent_agent._print_fn

    # Assign credential pool from parent (shared pool for leasing)
    parent_pool = _resolve_child_credential_pool(effective_provider, parent_agent)
    if parent_pool is not None:
        child._credential_pool = parent_pool

    # Set delegation depth so children can't spawn grandchildren
    child._delegate_depth = getattr(parent_agent, '_delegate_depth', 0) + 1

    # Register child for interrupt propagation
    if hasattr(parent_agent, '_active_children'):
        lock = getattr(parent_agent, '_active_children_lock', None)
        if lock:
            with lock:
                parent_agent._active_children.append(child)
        else:
            parent_agent._active_children.append(child)

    return child

def _run_single_child(
    task_index: int,
    goal: str,
    child=None,
    parent_agent=None,
    **_kwargs,
) -> Dict[str, Any]:
    """
    Run a pre-built child agent. Called from within a thread.
    Returns a structured result dict.
    """
    child_start = time.monotonic()

    # Get the progress callback from the child agent
    child_progress_cb = getattr(child, 'tool_progress_callback', None)

    # Restore parent tool names using the value saved before child construction
    # mutated the global. This is the correct parent toolset, not the child's.
    import model_tools
    _saved_tool_names = getattr(child, "_delegate_saved_tool_names",
                                list(model_tools._last_resolved_tool_names))

    # Acquire credential lease if pool is configured
    _pool = getattr(child, '_credential_pool', None)
    _leased_id = None
    if _pool is not None:
        try:
            _leased_id = _pool.acquire_lease()
            leased_entry = _pool.current()
            if leased_entry is not None and hasattr(child, '_swap_credential'):
                child._swap_credential(leased_entry)
        except Exception as _le:
            logger.debug("Credential lease acquisition failed: %s", _le)

    # Heartbeat: periodically propagate child activity to the parent so the
    # gateway inactivity timeout doesn't fire while the subagent is working.
    # Without this, the parent's _last_activity_ts freezes when delegate_task
    # starts and the gateway eventually kills the agent for "no activity".
    _heartbeat_stop = threading.Event()

    def _heartbeat_loop():
        while not _heartbeat_stop.wait(_HEARTBEAT_INTERVAL):
            if parent_agent is None:
                continue
            touch = getattr(parent_agent, '_touch_activity', None)
            if not touch:
                continue
            # Pull detail from the child's own activity tracker
            desc = f"delegate_task: subagent {task_index} working"
            try:
                child_summary = child.get_activity_summary()
                child_tool = child_summary.get("current_tool")
                child_iter = child_summary.get("api_call_count", 0)
                child_max = child_summary.get("max_iterations", 0)
                if child_tool:
                    desc = (f"delegate_task: subagent running {child_tool} "
                            f"(iteration {child_iter}/{child_max})")
                else:
                    child_desc = child_summary.get("last_activity_desc", "")
                    if child_desc:
                        desc = (f"delegate_task: subagent {child_desc} "
                                f"(iteration {child_iter}/{child_max})")
            except Exception:
                pass
            try:
                touch(desc)
            except Exception:
                pass

    _heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    _heartbeat_thread.start()

    try:
        result = child.run_conversation(user_message=goal)

        # Flush any remaining batched progress to gateway
        if child_progress_cb and hasattr(child_progress_cb, '_flush'):
            try:
                child_progress_cb._flush()
            except Exception as e:
                logger.debug("Progress callback flush failed: %s", e)

        duration = round(time.monotonic() - child_start, 2)

        summary = result.get("final_response") or ""
        completed = result.get("completed", False)
        interrupted = result.get("interrupted", False)
        api_calls = result.get("api_calls", 0)

        if interrupted:
            status = "interrupted"
        elif summary:
            # A summary means the subagent produced usable output.
            # exit_reason ("completed" vs "max_iterations") already
            # tells the parent *how* the task ended.
            status = "completed"
        else:
            status = "failed"

        # Build tool trace from conversation messages (already in memory).
        # Uses tool_call_id to correctly pair parallel tool calls with results.
        tool_trace: list[Dict[str, Any]] = []
        trace_by_id: Dict[str, Dict[str, Any]] = {}
        messages = result.get("messages") or []
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") == "assistant":
                    for tc in (msg.get("tool_calls") or []):
                        fn = tc.get("function", {})
                        entry_t = {
                            "tool": fn.get("name", "unknown"),
                            "args_bytes": len(fn.get("arguments", "")),
                        }
                        tool_trace.append(entry_t)
                        tc_id = tc.get("id")
                        if tc_id:
                            trace_by_id[tc_id] = entry_t
                elif msg.get("role") == "tool":
                    content = msg.get("content", "")
                    is_error = bool(
                        content and "error" in content[:80].lower()
                    )
                    result_meta = {
                        "result_bytes": len(content),
                        "status": "error" if is_error else "ok",
                    }
                    # Match by tool_call_id for parallel calls
                    tc_id = msg.get("tool_call_id")
                    target = trace_by_id.get(tc_id) if tc_id else None
                    if target is not None:
                        target.update(result_meta)
                    elif tool_trace:
                        # Fallback for messages without tool_call_id
                        tool_trace[-1].update(result_meta)

        # Determine exit reason
        if interrupted:
            exit_reason = "interrupted"
        elif completed:
            exit_reason = "completed"
        else:
            exit_reason = "max_iterations"

        # Extract token counts (safe for mock objects)
        _input_tokens = getattr(child, "session_prompt_tokens", 0)
        _output_tokens = getattr(child, "session_completion_tokens", 0)
        _model = getattr(child, "model", None)

        entry: Dict[str, Any] = {
            "task_index": task_index,
            "status": status,
            "summary": summary,
            "api_calls": api_calls,
            "duration_seconds": duration,
            "model": _model if isinstance(_model, str) else None,
            "exit_reason": exit_reason,
            "tokens": {
                "input": _input_tokens if isinstance(_input_tokens, (int, float)) else 0,
                "output": _output_tokens if isinstance(_output_tokens, (int, float)) else 0,
            },
            "tool_trace": tool_trace,
        }
        if status == "failed":
            entry["error"] = result.get("error", "Subagent did not produce a response.")

        return entry

    except Exception as exc:
        duration = round(time.monotonic() - child_start, 2)
        logging.exception(f"[subagent-{task_index}] failed")
        return {
            "task_index": task_index,
            "status": "error",
            "summary": None,
            "error": str(exc),
            "api_calls": 0,
            "duration_seconds": duration,
        }

    finally:
        # Stop the heartbeat thread so it doesn't keep touching parent activity
        # after the child has finished (or failed).
        _heartbeat_stop.set()
        _heartbeat_thread.join(timeout=5)

        if child_pool is not None and leased_cred_id is not None:
            try:
                child_pool.release_lease(leased_cred_id)
            except Exception as exc:
                logger.debug("Failed to release credential lease: %s", exc)

        # Restore the parent's tool names so the process-global is correct
        # for any subsequent execute_code calls or other consumers.
        import model_tools

        saved_tool_names = getattr(child, "_delegate_saved_tool_names", None)
        if isinstance(saved_tool_names, list):
            model_tools._last_resolved_tool_names = list(saved_tool_names)

        # Release credential lease if one was acquired
        if _pool is not None and _leased_id is not None:
            try:
                _pool.release_lease(_leased_id)
            except Exception as _lr:
                logger.debug("Credential lease release failed: %s", _lr)

        # Unregister child from interrupt propagation
        if hasattr(parent_agent, '_active_children'):
            try:
                lock = getattr(parent_agent, '_active_children_lock', None)
                if lock:
                    with lock:
                        parent_agent._active_children.remove(child)
                else:
                    parent_agent._active_children.remove(child)
            except (ValueError, UnboundLocalError) as e:
                logger.debug("Could not remove child from active_children: %s", e)

        # Close tool resources (terminal sandboxes, browser daemons,
        # background processes, httpx clients) so subagent subprocesses
        # don't outlive the delegation.
        try:
            if hasattr(child, 'close'):
                child.close()
        except Exception:
            logger.debug("Failed to close child agent after delegation")

def delegate_task(
    goal: Optional[str] = None,
    context: Optional[str] = None,
    toolsets: Optional[List[str]] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    max_iterations: Optional[int] = None,
    parent_agent=None,
    agent_name: Optional[str] = None,
) -> str:
    """
    Spawn one or more child agents to handle delegated tasks.

    Supports two modes:
      - Single: provide goal (+ optional context, toolsets)
      - Batch:  provide tasks array [{goal, context, toolsets}, ...]

    When agent_name is provided, the specialist is registered in the session
    registry and reused on subsequent calls with accumulated conversation history.

    Returns JSON with results array, one entry per task.
    """
    # ── Built-in agent type resolution ──────────────────────────────────────
    _builtin_def = None
    if agent_type:
        try:
            from agent.builtin_agents import get_agent_def
            _builtin_def = get_agent_def(agent_type)
            if _builtin_def is None:
                logger.warning("delegate_task: unknown agent_type %r — using generic", agent_type)
        except Exception as exc:
            logger.debug("delegate_task: builtin_agents import failed: %s", exc)

    # If a builtin def is found, prepend its system prompt as context injection
    # and apply its tool restrictions via allowed/blocked lists.
    if _builtin_def is not None and goal:
        # Prepend the persona — child sees it as additional system context
        persona_prefix = _builtin_def.system_prompt
        if context:
            context = f"{persona_prefix}\n\n---\n\n{context}"
        else:
            context = persona_prefix
        # Apply tool restrictions: convert allowed_tools to toolset list if set
        if _builtin_def.allowed_tools and toolsets is None:
            toolsets = _builtin_def.allowed_tools
        # Respect max_turns
        if max_iterations is None and _builtin_def.max_turns:
            max_iterations = _builtin_def.max_turns

    # ── Named agent snapshot injection ──────────────────────────────────────
    if agent_name:
        try:
            from agent.context_economy import get_agent_snapshot
            snapshot = get_agent_snapshot(agent_name)
            if snapshot:
                snapshot_prefix = f"## Your memory from the previous session\n{snapshot}\n\n---\n\n"
                context = snapshot_prefix + (context or "")
        except Exception as exc:
            logger.debug("delegate_task: snapshot injection failed: %s", exc)
    if parent_agent is None:
        return tool_error("delegate_task requires a parent agent context.")

    # A3: Named persistent specialist — reuse if already registered
    if agent_name:
        try:
            from agent.agent_registry import get_registry
            registry = get_registry()
            existing = registry.get(agent_name)
            if existing is not None and goal:
                # Reuse existing specialist with accumulated history
                accumulated_history = registry.get_history(agent_name)
                try:
                    result = existing.run_conversation(
                        user_message=goal,
                        conversation_history=accumulated_history,
                    )
                    registry.append_history(agent_name, result.get("messages", []))
                    return json.dumps({
                        "agent_name": agent_name,
                        "results": [{
                            "task_index": 0,
                            "status": "completed" if result.get("final_response") else "failed",
                            "summary": result.get("final_response", ""),
                            "exit_reason": "completed" if result.get("completed") else "max_iterations",
                            "api_calls": result.get("api_calls", 0),
                            "duration_seconds": 0,
                        }],
                        "total_duration_seconds": 0,
                    }, ensure_ascii=False)
                except Exception as exc:
                    logger.warning("agent_registry: specialist %r run failed: %s", agent_name, exc)
                    # Fall through to normal delegation
        except Exception as exc:
            logger.debug("agent_registry: lookup failed: %s", exc)

    # Depth limit
    depth = getattr(parent_agent, '_delegate_depth', 0)
    if depth >= MAX_DEPTH:
        return json.dumps({
            "error": (
                f"Delegation depth limit reached ({MAX_DEPTH}). "
                "Subagents cannot spawn further subagents."
            )
        })

    # Load config
    cfg = _load_config()
    default_max_iter = cfg.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    effective_max_iter = max_iterations or default_max_iter

    # Resolve delegation credentials (provider:model pair).
    # When delegation.provider is configured, this resolves the full credential
    # bundle (base_url, api_key, api_mode) via the same runtime provider system
    # used by CLI/gateway startup.  When unconfigured, returns None values so
    # children inherit from the parent.
    try:
        creds = _resolve_delegation_credentials(cfg, parent_agent)
    except ValueError as exc:
        return tool_error(str(exc))

    # Normalize to task list
    max_children = _get_max_concurrent_children()
    if tasks and isinstance(tasks, list):
        if len(tasks) > max_children:
            return tool_error(
                f"Too many tasks: {len(tasks)} provided, but "
                f"max_concurrent_children is {max_children}. "
                f"Either reduce the task count, split into multiple "
                f"delegate_task calls, or increase "
                f"delegation.max_concurrent_children in config.yaml."
            )
        task_list = tasks
    elif goal and isinstance(goal, str) and goal.strip():
        task_list = [{"goal": goal, "context": context, "toolsets": toolsets}]
    else:
        return tool_error("Provide either 'goal' (single task) or 'tasks' (batch).")

    if not task_list:
        return tool_error("No tasks provided.")

    # Validate each task has a goal
    for i, task in enumerate(task_list):
        if not task.get("goal", "").strip():
            return tool_error(f"Task {i} is missing a 'goal'.")

    # Emit delegation start hook (fire-and-forget)
    try:
        from hermes_cli.plugins import emit_hook as _emit_hook
        _emit_hook("on_delegation_start", goal=goal, toolsets=toolsets, tasks=tasks)
    except Exception:
        pass

    overall_start = time.monotonic()
    results = []

    n_tasks = len(task_list)
    # Track goal labels for progress display (truncated for readability)
    task_labels = [t["goal"][:40] for t in task_list]

    # Save parent tool names BEFORE any child construction mutates the global.
    # _build_child_agent() calls AIAgent() which calls get_tool_definitions(),
    # which overwrites model_tools._last_resolved_tool_names with child's toolset.
    import model_tools as _model_tools
    _parent_tool_names = list(_model_tools._last_resolved_tool_names)

    # Build all child agents on the main thread (thread-safe construction)
    # Wrapped in try/finally so the global is always restored even if a
    # child build raises (otherwise _last_resolved_tool_names stays corrupted).
    children = []
    try:
        for i, t in enumerate(task_list):
            child = _build_child_agent(
                task_index=i, goal=t["goal"], context=t.get("context"),
                toolsets=t.get("toolsets") or toolsets, model=creds["model"],
                max_iterations=effective_max_iter, parent_agent=parent_agent,
                override_provider=creds["provider"], override_base_url=creds["base_url"],
                override_api_key=creds["api_key"],
                override_api_mode=creds["api_mode"],
            )
            # Override with correct parent tool names (before child construction mutated global)
            child._delegate_saved_tool_names = _parent_tool_names
            # Register goal context so write_file lineage can attribute file writes
            try:
                from agent.lineage import set_task_context as _set_task_ctx
                _set_task_ctx(
                    getattr(child, "session_id", f"child-{i}"),
                    t["goal"],
                    session_id=getattr(child, "session_id", ""),
                    model=creds.get("model", ""),
                )
            except Exception:
                pass
            children.append((i, t, child))
    finally:
        # Authoritative restore: reset global to parent's tool names after all children built
        _model_tools._last_resolved_tool_names = _parent_tool_names

    if n_tasks == 1:
        # Single task -- run directly (no thread pool overhead)
        _i, _t, child = children[0]
        result = _run_single_child(0, _t["goal"], child, parent_agent)
        results.append(result)
        # Record cost for single-task delegations too
        try:
            from agent.lineage import record_task_cost as _rec_cost1
            _stok = result.get("tokens", {})
            _rec_cost1(
                label=task_labels[0] if task_labels else _t["goal"][:40],
                model=result.get("model") or creds.get("model", ""),
                input_tokens=int(_stok.get("input", 0)),
                output_tokens=int(_stok.get("output", 0)),
                status=result.get("status", "completed"),
                duration_seconds=float(result.get("duration_seconds", 0)),
                session_id=getattr(parent_agent, "session_id", ""),
            )
        except Exception:
            pass
    else:
        # Batch -- run in parallel with per-task progress lines
        completed_count = 0
        spinner_ref = getattr(parent_agent, '_delegate_spinner', None)

        with ThreadPoolExecutor(max_workers=max_children) as executor:
            futures = {}
            for i, t, child in children:
                future = executor.submit(
                    _run_single_child,
                    task_index=i,
                    goal=t["goal"],
                    child=child,
                    parent_agent=parent_agent,
                )
                futures[future] = i

            for future in as_completed(futures):
                try:
                    entry = future.result()
                except Exception as exc:
                    idx = futures[future]
                    entry = {
                        "task_index": idx,
                        "status": "error",
                        "summary": None,
                        "error": str(exc),
                        "api_calls": 0,
                        "duration_seconds": 0,
                    }
                results.append(entry)
                completed_count += 1

                # Print per-task completion line above the spinner
                idx = entry["task_index"]
                label = task_labels[idx] if idx < len(task_labels) else f"Task {idx}"
                dur = entry.get("duration_seconds", 0)
                status = entry.get("status", "?")
                icon = "✓" if status == "completed" else "✗"
                remaining = n_tasks - completed_count

                # Record cost and build cost suffix
                _tok = entry.get("tokens", {})
                _in_tok = int(_tok.get("input", 0))
                _out_tok = int(_tok.get("output", 0))
                _entry_model = entry.get("model") or creds.get("model", "")
                _cost_suffix = ""
                try:
                    from agent.lineage import record_task_cost as _rec_cost
                    _rec_cost(
                        label=label,
                        model=_entry_model,
                        input_tokens=_in_tok,
                        output_tokens=_out_tok,
                        status=status,
                        duration_seconds=float(dur),
                        session_id=getattr(parent_agent, "session_id", ""),
                    )
                    from agent.usage_pricing import CanonicalUsage, estimate_usage_cost as _esc
                    _cr = _esc(_entry_model, CanonicalUsage(input_tokens=_in_tok, output_tokens=_out_tok))
                    if _cr.amount_usd is not None:
                        _cost_suffix = f"  ~${float(_cr.amount_usd):.4f}"
                    elif _cr.status == "included":
                        _cost_suffix = "  included"
                    if _in_tok or _out_tok:
                        _cost_suffix += f"  ({_in_tok:,}in / {_out_tok:,}out)"
                except Exception:
                    pass

                completion_line = f"{icon} [{idx+1}/{n_tasks}] {label}  ({dur}s){_cost_suffix}"
                if spinner_ref:
                    try:
                        spinner_ref.print_above(completion_line)
                    except Exception:
                        print(f"  {completion_line}")
                else:
                    print(f"  {completion_line}")

                # Update spinner text to show remaining count
                if spinner_ref and remaining > 0:
                    try:
                        spinner_ref.update_text(f"🔀 {remaining} task{'s' if remaining != 1 else ''} remaining")
                    except Exception as e:
                        logger.debug("Spinner update_text failed: %s", e)

        # Sort by task_index so results match input order
        results.sort(key=lambda r: r["task_index"])

    total_duration = round(time.monotonic() - overall_start, 2)

    # Emit delegation end hook (fire-and-forget)
    try:
        from hermes_cli.plugins import emit_hook as _emit_hook
        _success = all(r.get("status") not in ("error", "failed") for r in results)
        _emit_hook("on_delegation_end", goal=goal, success=_success, results=results)
    except Exception:
        pass

    # A3: Register the specialist in the session registry so it can be reused
    if agent_name and n_tasks == 1 and children:
        try:
            from agent.agent_registry import get_registry
            _i, _t, child = children[0]
            registry = get_registry()
            registry.register(agent_name, child)
            # Seed history from the child's conversation messages
            result_messages = results[0].get("messages", []) if results else []
            if result_messages:
                registry.append_history(agent_name, result_messages)
            logger.debug("agent_registry: registered specialist %r", agent_name)
        except Exception as exc:
            logger.debug("agent_registry: registration failed: %s", exc)

    return json.dumps({
        "results": results,
        "total_duration_seconds": total_duration,
    }, ensure_ascii=False)


def _resolve_child_credential_pool(effective_provider: Optional[str], parent_agent):
    """Resolve a credential pool for the child agent.

    Rules:
    1. Same provider as the parent -> share the parent's pool so cooldown state
       and rotation stay synchronized.
    2. Different provider -> try to load that provider's own pool.
    3. No pool available -> return None and let the child keep the inherited
       fixed credential behavior.
    """
    if not effective_provider:
        return getattr(parent_agent, "_credential_pool", None)

    parent_provider = getattr(parent_agent, "provider", None) or ""
    parent_pool = getattr(parent_agent, "_credential_pool", None)
    if parent_pool is not None and effective_provider == parent_provider:
        return parent_pool

    try:
        from agent.credential_pool import load_pool
        pool = load_pool(effective_provider)
        if pool is not None and pool.has_credentials():
            return pool
    except Exception as exc:
        logger.debug(
            "Could not load credential pool for child provider '%s': %s",
            effective_provider,
            exc,
        )
    return None


def _resolve_delegation_credentials(cfg: dict, parent_agent) -> dict:
    """Resolve credentials for subagent delegation.

    If ``delegation.base_url`` is configured, subagents use that direct
    OpenAI-compatible endpoint. Otherwise, if ``delegation.provider`` is
    configured, the full credential bundle (base_url, api_key, api_mode,
    provider) is resolved via the runtime provider system — the same path used
    by CLI/gateway startup. This lets subagents run on a completely different
    provider:model pair.

    If neither base_url nor provider is configured, returns None values so the
    child inherits everything from the parent agent.

    Raises ValueError with a user-friendly message on credential failure.
    """
    configured_model = str(cfg.get("model") or "").strip() or None
    configured_provider = str(cfg.get("provider") or "").strip() or None
    configured_base_url = str(cfg.get("base_url") or "").strip() or None
    configured_api_key = str(cfg.get("api_key") or "").strip() or None

    if configured_base_url:
        api_key = (
            configured_api_key
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        if not api_key:
            raise ValueError(
                "Delegation base_url is configured but no API key was found. "
                "Set delegation.api_key or OPENAI_API_KEY."
            )

        base_lower = configured_base_url.lower()
        provider = "custom"
        api_mode = "chat_completions"
        if "chatgpt.com/backend-api/codex" in base_lower:
            provider = "openai-codex"
            api_mode = "codex_responses"
        elif "api.anthropic.com" in base_lower:
            provider = "anthropic"
            api_mode = "anthropic_messages"

        return {
            "model": configured_model,
            "provider": provider,
            "base_url": configured_base_url,
            "api_key": api_key,
            "api_mode": api_mode,
        }

    if not configured_provider:
        # No provider override — child inherits everything from parent
        return {
            "model": configured_model,
            "provider": None,
            "base_url": None,
            "api_key": None,
            "api_mode": None,
        }

    # Provider is configured — resolve full credentials
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider
        runtime = resolve_runtime_provider(requested=configured_provider)
    except Exception as exc:
        raise ValueError(
            f"Cannot resolve delegation provider '{configured_provider}': {exc}. "
            f"Check that the provider is configured (API key set, valid provider name), "
            f"or set delegation.base_url/delegation.api_key for a direct endpoint. "
            f"Available providers: openrouter, nous, zai, kimi-coding, minimax."
        ) from exc

    api_key = runtime.get("api_key", "")
    if not api_key:
        raise ValueError(
            f"Delegation provider '{configured_provider}' resolved but has no API key. "
            f"Set the appropriate environment variable or run 'hermes login'."
        )

    return {
        "model": configured_model,
        "provider": runtime.get("provider"),
        "base_url": runtime.get("base_url"),
        "api_key": api_key,
        "api_mode": runtime.get("api_mode"),
        "command": runtime.get("command"),
        "args": list(runtime.get("args") or []),
    }


def _load_config() -> dict:
    """Load delegation config from CLI_CONFIG or persistent config.

    Checks the runtime config (cli.py CLI_CONFIG) first, then falls back
    to the persistent config (hermes_cli/config.py load_config()) so that
    ``delegation.model`` / ``delegation.provider`` are picked up regardless
    of the entry point (CLI, gateway, cron).
    """
    try:
        from cli import CLI_CONFIG
        cfg = CLI_CONFIG.get("delegation", {})
        if cfg:
            return cfg
    except Exception:
        pass
    try:
        from hermes_cli.config import load_config
        full = load_config()
        return full.get("delegation", {})
    except Exception:
        return {}


def delegate_task_async(
    goal: str,
    context: str = None,
    toolsets: list = None,
    tasks: list = None,
    max_iterations: int = None,
    parent_agent=None,
) -> str:
    """Start delegation in a background thread. Returns task_handle_id immediately.

    Parent agent can continue working while the subagent runs.
    Use check_delegation(task_handle_id) to poll for results.
    """
    import threading
    from agent.mailbox import get_mailbox

    mailbox = get_mailbox()
    handle = mailbox.reserve()

    def _run():
        try:
            result = delegate_task(
                goal=goal,
                context=context,
                toolsets=toolsets,
                tasks=tasks,
                max_iterations=max_iterations,
                parent_agent=parent_agent,
            )
            if isinstance(result, str):
                import json
                try:
                    result = json.loads(result)
                except Exception:
                    result = {"response": result}
            mailbox.send(handle, result)
        except Exception as e:
            mailbox.send(handle, {"error": str(e), "failed": True})

    thread = threading.Thread(target=_run, daemon=True, name=f"delegate-{handle}")
    thread.start()

    import json
    return json.dumps({
        "task_handle_id": handle,
        "status": "running",
        "message": "Delegation started in background. Use check_delegation to poll for results.",
    })


def check_delegation(task_handle_id: str, wait_seconds: float = 0) -> str:
    """Check if an async delegation has completed.

    Args:
        task_handle_id: The handle returned by delegate_task_async
        wait_seconds: How long to wait (0 = non-blocking poll, >0 = wait up to N seconds)

    Returns JSON with status: "pending" | "completed" | "not_found"
    """
    import json
    from agent.mailbox import get_mailbox

    mailbox = get_mailbox()

    if wait_seconds > 0:
        result = mailbox.receive(task_handle_id, timeout=wait_seconds)
    else:
        result = mailbox.poll(task_handle_id)

    if result is None:
        return json.dumps({"status": "pending", "task_handle_id": task_handle_id})

    mailbox.discard(task_handle_id)
    return json.dumps({
        "status": "completed",
        "task_handle_id": task_handle_id,
        "result": result,
    })


# ---------------------------------------------------------------------------
# OpenAI Function-Calling Schema
# ---------------------------------------------------------------------------

DELEGATE_TASK_SCHEMA = {
    "name": "delegate_task",
    "description": (
        "Spawn one or more subagents to work on tasks in isolated contexts. "
        "Each subagent gets its own conversation, terminal session, and toolset. "
        "Only the final summary is returned -- intermediate tool results "
        "never enter your context window.\n\n"
        "TWO MODES (one of 'goal' or 'tasks' is required):\n"
        "1. Single task: provide 'goal' (+ optional context, toolsets)\n"
        "2. Batch (parallel): provide 'tasks' array with up to 3 items. "
        "All run concurrently and results are returned together.\n\n"
        "WHEN TO USE delegate_task:\n"
        "- Reasoning-heavy subtasks (debugging, code review, research synthesis)\n"
        "- Tasks that would flood your context with intermediate data\n"
        "- Parallel independent workstreams (research A and B simultaneously)\n\n"
        "WHEN NOT TO USE (use these instead):\n"
        "- Mechanical multi-step work with no reasoning needed -> use execute_code\n"
        "- Single tool call -> just call the tool directly\n"
        "- Tasks needing user interaction -> subagents cannot use clarify\n\n"
        "IMPORTANT:\n"
        "- Subagents have NO memory of your conversation. Pass all relevant "
        "info (file paths, error messages, constraints) via the 'context' field.\n"
        "- Subagents CANNOT call: delegate_task, clarify, memory, send_message, "
        "execute_code.\n"
        "- Each subagent gets its own terminal session (separate working directory and state).\n"
        "- Results are always returned as an array, one entry per task."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "What the subagent should accomplish. Be specific and "
                    "self-contained -- the subagent knows nothing about your "
                    "conversation history."
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Background information the subagent needs: file paths, "
                    "error messages, project structure, constraints. The more "
                    "specific you are, the better the subagent performs."
                ),
            },
            "toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Toolsets to enable for this subagent. "
                    "Default: inherits your enabled toolsets. "
                    "Common patterns: ['terminal', 'file'] for code work, "
                    "['web'] for research, ['terminal', 'file', 'web'] for "
                    "full-stack tasks."
                ),
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "Task goal"},
                        "context": {"type": "string", "description": "Task-specific context"},
                        "toolsets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Toolsets for this specific task",
                        },
                    },
                    "required": ["goal"],
                },
                # No maxItems — the runtime limit is configurable via
                # delegation.max_concurrent_children (default 3) and
                # enforced with a clear error in delegate_task().
                "description": (
                    "Batch mode: tasks to run in parallel (limit configurable via delegation.max_concurrent_children, default 3). Each gets "
                    "its own subagent with isolated context and terminal session. "
                    "When provided, top-level goal/context/toolsets are ignored."
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": (
                    "Max tool-calling turns per subagent (default: 50). "
                    "Only set lower for simple tasks."
                ),
            },
            "agent_name": {
                "type": "string",
                "description": (
                    "Optional. Name this specialist (e.g. 'researcher', 'coder'). "
                    "Named specialists are registered in the session registry and can "
                    "be reused via message_agent or subsequent delegate_task calls "
                    "with the same agent_name. The specialist retains accumulated "
                    "conversation history across calls."
                ),
            },
        },
        "required": [],
    },
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="delegate_task",
    toolset="delegation",
    schema=DELEGATE_TASK_SCHEMA,
    handler=lambda args, **kw: delegate_task(
        goal=args.get("goal"),
        context=args.get("context"),
        toolsets=args.get("toolsets"),
        tasks=args.get("tasks"),
        max_iterations=args.get("max_iterations"),
        parent_agent=kw.get("parent_agent"),
        agent_name=args.get("agent_name")),
    check_fn=check_delegate_requirements,
    emoji="🔀",
)

DELEGATE_TASK_ASYNC_SCHEMA = {
    "name": "delegate_task_async",
    "description": (
        "Start a delegation in the background and return a task_handle_id immediately. "
        "The parent agent can continue working while the subagent runs in a background thread. "
        "Use check_delegation(task_handle_id) to poll for results.\n\n"
        "Same semantics as delegate_task but non-blocking: returns immediately with a handle "
        "instead of waiting for the subagent to finish.\n\n"
        "WHEN TO USE:\n"
        "- When you want to start a long-running subagent task and continue doing other work\n"
        "- When running multiple independent subagents concurrently without batch mode\n\n"
        "IMPORTANT:\n"
        "- Subagents have NO memory of your conversation. Pass all relevant info via 'context'.\n"
        "- Use check_delegation with the returned task_handle_id to get results."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "What the subagent should accomplish.",
            },
            "context": {
                "type": "string",
                "description": "Background information the subagent needs.",
            },
            "toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Toolsets to enable for this subagent.",
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "context": {"type": "string"},
                        "toolsets": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["goal"],
                },
                "maxItems": 3,
                "description": "Batch mode: up to 3 tasks to run in parallel.",
            },
            "max_iterations": {
                "type": "integer",
                "description": "Max tool-calling turns per subagent (default: 50).",
            },
        },
        "required": [],
    },
}

registry.register(
    name="delegate_task_async",
    toolset="delegation",
    schema=DELEGATE_TASK_ASYNC_SCHEMA,
    handler=lambda args, **kw: delegate_task_async(
        goal=args.get("goal"),
        context=args.get("context"),
        toolsets=args.get("toolsets"),
        tasks=args.get("tasks"),
        max_iterations=args.get("max_iterations"),
        parent_agent=kw.get("parent_agent")),
    check_fn=check_delegate_requirements,
    emoji="🔀",
)

CHECK_DELEGATION_SCHEMA = {
    "name": "check_delegation",
    "description": (
        "Check if an async delegation started with delegate_task_async has completed.\n\n"
        "Returns status: 'pending' (still running) or 'completed' (result available).\n\n"
        "Use wait_seconds > 0 to block until the task finishes (up to N seconds).\n"
        "Use wait_seconds = 0 (default) for a non-blocking poll."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_handle_id": {
                "type": "string",
                "description": "The handle returned by delegate_task_async.",
            },
            "wait_seconds": {
                "type": "number",
                "description": (
                    "How long to wait for results. "
                    "0 = non-blocking poll (default). "
                    ">0 = block up to N seconds."
                ),
            },
        },
        "required": ["task_handle_id"],
    },
}

registry.register(
    name="check_delegation",
    toolset="delegation",
    schema=CHECK_DELEGATION_SCHEMA,
    handler=lambda args, **kw: check_delegation(
        task_handle_id=args.get("task_handle_id"),
        wait_seconds=args.get("wait_seconds", 0)),
    check_fn=check_delegate_requirements,
    emoji="🔀",
)


def message_agent(name: str, message: str) -> str:
    """Send a follow-up message to a named specialist agent.

    The specialist already has context from previous interactions.
    Use this instead of delegate_task when continuing work with a named agent.
    """
    from agent.agent_registry import get_registry

    registry = get_registry()
    specialist = registry.get(name)
    if specialist is None:
        return json.dumps({
            "error": (
                f"No specialist named {name!r}. "
                f"Create one with delegate_task(agent_name='{name}', ...) first."
            )
        })

    try:
        history = registry.get_history(name)
        result = specialist.run_conversation(
            user_message=message,
            conversation_history=history,
        )
        registry.append_history(name, result.get("messages", []))

        return json.dumps({
            "agent_name": name,
            "response": result.get("final_response", ""),
            "completed": result.get("completed", False),
        }, ensure_ascii=False)
    except Exception as exc:
        logger.warning("message_agent: specialist %r failed: %s", name, exc)
        return json.dumps({
            "error": f"Specialist {name!r} run failed: {exc}",
            "agent_name": name,
        })


MESSAGE_AGENT_SCHEMA = {
    "name": "message_agent",
    "description": (
        "Send a follow-up message to a named specialist agent created via delegate_task.\n\n"
        "The specialist retains full context from all previous interactions, making it a "
        "true persistent specialist you can continue a conversation with.\n\n"
        "WHEN TO USE:\n"
        "- You already created a specialist with delegate_task(agent_name='...', ...)\n"
        "- You want to continue work with that same specialist (ask follow-ups, iterate)\n"
        "- The specialist has context that would be expensive to re-establish\n\n"
        "WHEN TO USE delegate_task INSTEAD:\n"
        "- First interaction with a specialist (use agent_name param there)\n"
        "- Parallel work with multiple specialists\n\n"
        "The specialist's response is returned directly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The specialist agent name (as passed to delegate_task agent_name).",
            },
            "message": {
                "type": "string",
                "description": "The follow-up message or instruction to send.",
            },
        },
        "required": ["name", "message"],
    },
}

registry.register(
    name="message_agent",
    toolset="delegation",
    schema=MESSAGE_AGENT_SCHEMA,
    handler=lambda args, **kw: message_agent(
        name=args.get("name", ""),
        message=args.get("message", ""),
    ),
    check_fn=check_delegate_requirements,
    emoji="🔀",
)
