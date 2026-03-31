# agent/tool_executor.py
"""
Tool execution layer extracted from run_agent.AIAgent.

ToolExecutor wraps the four tool-dispatching methods so they can be
tested in isolation and reused by future async/streaming paths.
All behavior is identical to the original in-class versions.
"""
from __future__ import annotations
import json
import logging
import os
import random
import time
import concurrent.futures
from typing import TYPE_CHECKING

from model_tools import handle_function_call

if TYPE_CHECKING:
    from run_agent import AIAgent

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tool calls on behalf of an AIAgent instance.

    All methods operate on the agent's state via the ``agent`` reference.
    This keeps the extraction purely structural: behavior is identical
    to the in-class versions.
    """

    def __init__(self, agent: "AIAgent") -> None:
        self.agent = agent

    def invoke_tool(self, function_name: str, function_args: dict, effective_task_id: str) -> str:
        """Invoke a single tool and return the result string. No display logic.

        Handles both agent-level tools (todo, memory, etc.) and registry-dispatched
        tools. Used by the concurrent execution path; the sequential path retains
        its own inline invocation for backward-compatible display handling.
        """
        if function_name == "todo":
            from tools.todo_tool import todo_tool as _todo_tool
            return _todo_tool(
                todos=function_args.get("todos"),
                merge=function_args.get("merge", False),
                store=self.agent._todo_store,
            )
        elif function_name == "session_search":
            if not self.agent._session_db:
                return json.dumps({"success": False, "error": "Session database not available."})
            from tools.session_search_tool import session_search as _session_search
            return _session_search(
                query=function_args.get("query", ""),
                role_filter=function_args.get("role_filter"),
                limit=function_args.get("limit", 3),
                db=self.agent._session_db,
                current_session_id=self.agent.session_id,
            )
        elif function_name == "memory":
            target = function_args.get("target", "memory")
            from tools.memory_tool import memory_tool as _memory_tool
            result = _memory_tool(
                action=function_args.get("action"),
                target=target,
                content=function_args.get("content"),
                old_text=function_args.get("old_text"),
                store=self.agent._memory_store,
            )
            # Also send user observations to Honcho when active
            if self.agent._honcho and target == "user" and function_args.get("action") == "add":
                self.agent._honcho_save_user_observation(function_args.get("content", ""))
            return result
        elif function_name == "clarify":
            from tools.clarify_tool import clarify_tool as _clarify_tool
            return _clarify_tool(
                question=function_args.get("question", ""),
                choices=function_args.get("choices"),
                callback=self.agent.clarify_callback,
            )
        elif function_name == "delegate_task":
            from tools.delegate_tool import delegate_task as _delegate_task
            return _delegate_task(
                goal=function_args.get("goal"),
                context=function_args.get("context"),
                toolsets=function_args.get("toolsets"),
                tasks=function_args.get("tasks"),
                max_iterations=function_args.get("max_iterations"),
                parent_agent=self.agent,
            )
        else:
            return handle_function_call(
                function_name, function_args, effective_task_id,
                enabled_tools=list(self.agent.valid_tool_names) if self.agent.valid_tool_names else None,
                honcho_manager=self.agent._honcho,
                honcho_session_key=self.agent._honcho_session_key,
            )

    def execute_concurrent(self, assistant_message, messages: list, effective_task_id: str, api_call_count: int = 0) -> None:
        """Execute multiple tool calls concurrently using a thread pool.

        Results are collected in the original tool-call order and appended to
        messages so the API sees them in the expected sequence.
        """
        from run_agent import (
            _should_parallelize_tool_batch, _is_destructive_command,
            _detect_tool_failure, _build_tool_preview, _get_cute_tool_message_impl,
            _MAX_TOOL_WORKERS, KawaiiSpinner,
        )
        tool_calls = assistant_message.tool_calls
        num_tools = len(tool_calls)

        # ── Pre-flight: interrupt check ──────────────────────────────────
        if self.agent._interrupt_requested:
            print(f"{self.agent.log_prefix}⚡ Interrupt: skipping {num_tools} tool call(s)")
            for tc in tool_calls:
                messages.append({
                    "role": "tool",
                    "content": f"[Tool execution cancelled — {tc.function.name} was skipped due to user interrupt]",
                    "tool_call_id": tc.id,
                })
            return

        # ── Parse args + pre-execution bookkeeping ───────────────────────
        parsed_calls = []  # list of (tool_call, function_name, function_args)
        for tool_call in tool_calls:
            function_name = tool_call.function.name

            # Reset nudge counters
            if function_name == "memory":
                self.agent._turns_since_memory = 0
            elif function_name == "skill_manage":
                self.agent._iters_since_skill = 0

            try:
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                function_args = {}
            if not isinstance(function_args, dict):
                function_args = {}

            # Checkpoint for file-mutating tools
            if function_name in ("write_file", "patch") and self.agent._checkpoint_mgr.enabled:
                try:
                    file_path = function_args.get("path", "")
                    if file_path:
                        work_dir = self.agent._checkpoint_mgr.get_working_dir_for_path(file_path)
                        self.agent._checkpoint_mgr.ensure_checkpoint(work_dir, f"before {function_name}")
                except Exception:
                    pass

            # Checkpoint before destructive terminal commands
            if function_name == "terminal" and self.agent._checkpoint_mgr.enabled:
                try:
                    cmd = function_args.get("command", "")
                    if _is_destructive_command(cmd):
                        cwd = function_args.get("workdir") or os.getenv("TERMINAL_CWD", os.getcwd())
                        self.agent._checkpoint_mgr.ensure_checkpoint(
                            cwd, f"before terminal: {cmd[:60]}"
                        )
                except Exception:
                    pass

            parsed_calls.append((tool_call, function_name, function_args))

        # ── Logging / callbacks ──────────────────────────────────────────
        tool_names_str = ", ".join(name for _, name, _ in parsed_calls)
        if not self.agent.quiet_mode:
            print(f"  ⚡ Concurrent: {num_tools} tool calls — {tool_names_str}")
            for i, (tc, name, args) in enumerate(parsed_calls, 1):
                args_str = json.dumps(args, ensure_ascii=False)
                if self.agent.verbose_logging:
                    print(f"  📞 Tool {i}: {name}({list(args.keys())})")
                    print(f"     Args: {args_str}")
                else:
                    args_preview = args_str[:self.agent.log_prefix_chars] + "..." if len(args_str) > self.agent.log_prefix_chars else args_str
                    print(f"  📞 Tool {i}: {name}({list(args.keys())}) - {args_preview}")

        for _, name, args in parsed_calls:
            if self.agent.tool_progress_callback:
                try:
                    preview = _build_tool_preview(name, args)
                    self.agent.tool_progress_callback(name, preview, args)
                except Exception as cb_err:
                    logging.debug(f"Tool progress callback error: {cb_err}")

        # ── Concurrent execution ─────────────────────────────────────────
        # Each slot holds (function_name, function_args, function_result, duration, error_flag)
        results = [None] * num_tools

        def _run_tool(index, tool_call, function_name, function_args):
            """Worker function executed in a thread."""
            start = time.time()
            try:
                result = self.invoke_tool(function_name, function_args, effective_task_id)
            except Exception as tool_error:
                result = f"Error executing tool '{function_name}': {tool_error}"
                logger.error("_invoke_tool raised for %s: %s", function_name, tool_error, exc_info=True)
            duration = time.time() - start
            is_error, _ = _detect_tool_failure(function_name, result)
            results[index] = (function_name, function_args, result, duration, is_error)

        # Start spinner for CLI mode (skip when TUI handles tool progress)
        spinner = None
        if self.agent.quiet_mode and not self.agent.tool_progress_callback:
            face = random.choice(KawaiiSpinner.KAWAII_WAITING)
            spinner = KawaiiSpinner(f"{face} ⚡ running {num_tools} tools concurrently", spinner_type='dots', print_fn=self.agent._print_fn)
            spinner.start()

        try:
            max_workers = min(num_tools, _MAX_TOOL_WORKERS)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for i, (tc, name, args) in enumerate(parsed_calls):
                    f = executor.submit(_run_tool, i, tc, name, args)
                    futures.append(f)

                # Wait for all to complete (exceptions are captured inside _run_tool)
                concurrent.futures.wait(futures)
        finally:
            if spinner:
                # Build a summary message for the spinner stop
                completed = sum(1 for r in results if r is not None)
                total_dur = sum(r[3] for r in results if r is not None)
                spinner.stop(f"⚡ {completed}/{num_tools} tools completed in {total_dur:.1f}s total")

        # ── Post-execution: display per-tool results ─────────────────────
        for i, (tc, name, args) in enumerate(parsed_calls):
            r = results[i]
            if r is None:
                # Shouldn't happen, but safety fallback
                function_result = f"Error executing tool '{name}': thread did not return a result"
                tool_duration = 0.0
            else:
                function_name, function_args, function_result, tool_duration, is_error = r

                if is_error:
                    result_preview = function_result[:200] if len(function_result) > 200 else function_result
                    logger.warning("Tool %s returned error (%.2fs): %s", function_name, tool_duration, result_preview)

                if self.agent.verbose_logging:
                    logging.debug(f"Tool {function_name} completed in {tool_duration:.2f}s")
                    logging.debug(f"Tool result ({len(function_result)} chars): {function_result}")

            # Print cute message per tool
            if self.agent.quiet_mode:
                cute_msg = _get_cute_tool_message_impl(name, args, tool_duration, result=function_result)
                self.agent._safe_print(f"  {cute_msg}")
            elif not self.agent.quiet_mode:
                if self.agent.verbose_logging:
                    print(f"  ✅ Tool {i+1} completed in {tool_duration:.2f}s")
                    print(f"     Result: {function_result}")
                else:
                    response_preview = function_result[:self.agent.log_prefix_chars] + "..." if len(function_result) > self.agent.log_prefix_chars else function_result
                    print(f"  ✅ Tool {i+1} completed in {tool_duration:.2f}s - {response_preview}")

            # Truncate oversized results
            MAX_TOOL_RESULT_CHARS = 100_000
            if len(function_result) > MAX_TOOL_RESULT_CHARS:
                original_len = len(function_result)
                function_result = (
                    function_result[:MAX_TOOL_RESULT_CHARS]
                    + f"\n\n[Truncated: tool response was {original_len:,} chars, "
                    f"exceeding the {MAX_TOOL_RESULT_CHARS:,} char limit]"
                )

            # Append tool result message in order
            tool_msg = {
                "role": "tool",
                "content": function_result,
                "tool_call_id": tc.id,
            }
            messages.append(tool_msg)

        # ── Budget pressure injection ────────────────────────────────────
        budget_warning = self.agent._get_budget_warning(api_call_count)
        if budget_warning and messages and messages[-1].get("role") == "tool":
            last_content = messages[-1]["content"]
            try:
                parsed = json.loads(last_content)
                if isinstance(parsed, dict):
                    parsed["_budget_warning"] = budget_warning
                    messages[-1]["content"] = json.dumps(parsed, ensure_ascii=False)
                else:
                    messages[-1]["content"] = last_content + f"\n\n{budget_warning}"
            except (json.JSONDecodeError, TypeError):
                messages[-1]["content"] = last_content + f"\n\n{budget_warning}"
            if not self.agent.quiet_mode:
                remaining = self.agent.max_iterations - api_call_count
                tier = "⚠️  WARNING" if remaining <= self.agent.max_iterations * 0.1 else "💡 CAUTION"
                print(f"{self.agent.log_prefix}{tier}: {remaining} iterations remaining")

    def execute_sequential(self, assistant_message, messages: list, effective_task_id: str, api_call_count: int = 0) -> None:
        """Execute tool calls sequentially (original behavior). Used for single calls or interactive tools."""
        from run_agent import (
            _is_destructive_command, _detect_tool_failure, _build_tool_preview,
            _get_cute_tool_message_impl, _get_tool_emoji, KawaiiSpinner,
        )
        for i, tool_call in enumerate(assistant_message.tool_calls, 1):
            # SAFETY: check interrupt BEFORE starting each tool.
            # If the user sent "stop" during a previous tool's execution,
            # do NOT start any more tools -- skip them all immediately.
            if self.agent._interrupt_requested:
                remaining_calls = assistant_message.tool_calls[i-1:]
                if remaining_calls:
                    self.agent._vprint(f"{self.agent.log_prefix}⚡ Interrupt: skipping {len(remaining_calls)} tool call(s)", force=True)
                for skipped_tc in remaining_calls:
                    skipped_name = skipped_tc.function.name
                    skip_msg = {
                        "role": "tool",
                        "content": f"[Tool execution cancelled — {skipped_name} was skipped due to user interrupt]",
                        "tool_call_id": skipped_tc.id,
                    }
                    messages.append(skip_msg)
                break

            function_name = tool_call.function.name

            # Reset nudge counters when the relevant tool is actually used
            if function_name == "memory":
                self.agent._turns_since_memory = 0
            elif function_name == "skill_manage":
                self.agent._iters_since_skill = 0

            try:
                function_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                logging.warning(f"Unexpected JSON error after validation: {e}")
                function_args = {}
            if not isinstance(function_args, dict):
                function_args = {}

            if not self.agent.quiet_mode:
                args_str = json.dumps(function_args, ensure_ascii=False)
                if self.agent.verbose_logging:
                    print(f"  📞 Tool {i}: {function_name}({list(function_args.keys())})")
                    print(f"     Args: {args_str}")
                else:
                    args_preview = args_str[:self.agent.log_prefix_chars] + "..." if len(args_str) > self.agent.log_prefix_chars else args_str
                    print(f"  📞 Tool {i}: {function_name}({list(function_args.keys())}) - {args_preview}")

            if self.agent.tool_progress_callback:
                try:
                    preview = _build_tool_preview(function_name, function_args)
                    self.agent.tool_progress_callback(function_name, preview, function_args)
                except Exception as cb_err:
                    logging.debug(f"Tool progress callback error: {cb_err}")

            # Checkpoint: snapshot working dir before file-mutating tools
            if function_name in ("write_file", "patch") and self.agent._checkpoint_mgr.enabled:
                try:
                    file_path = function_args.get("path", "")
                    if file_path:
                        work_dir = self.agent._checkpoint_mgr.get_working_dir_for_path(file_path)
                        self.agent._checkpoint_mgr.ensure_checkpoint(
                            work_dir, f"before {function_name}"
                        )
                except Exception:
                    pass  # never block tool execution

            # Checkpoint before destructive terminal commands
            if function_name == "terminal" and self.agent._checkpoint_mgr.enabled:
                try:
                    cmd = function_args.get("command", "")
                    if _is_destructive_command(cmd):
                        cwd = function_args.get("workdir") or os.getenv("TERMINAL_CWD", os.getcwd())
                        self.agent._checkpoint_mgr.ensure_checkpoint(
                            cwd, f"before terminal: {cmd[:60]}"
                        )
                except Exception:
                    pass  # never block tool execution

            tool_start_time = time.time()

            if function_name == "todo":
                from tools.todo_tool import todo_tool as _todo_tool
                function_result = _todo_tool(
                    todos=function_args.get("todos"),
                    merge=function_args.get("merge", False),
                    store=self.agent._todo_store,
                )
                tool_duration = time.time() - tool_start_time
                if self.agent.quiet_mode:
                    self.agent._vprint(f"  {_get_cute_tool_message_impl('todo', function_args, tool_duration, result=function_result)}")
            elif function_name == "session_search":
                if not self.agent._session_db:
                    function_result = json.dumps({"success": False, "error": "Session database not available."})
                else:
                    from tools.session_search_tool import session_search as _session_search
                    function_result = _session_search(
                        query=function_args.get("query", ""),
                        role_filter=function_args.get("role_filter"),
                        limit=function_args.get("limit", 3),
                        db=self.agent._session_db,
                        current_session_id=self.agent.session_id,
                    )
                tool_duration = time.time() - tool_start_time
                if self.agent.quiet_mode:
                    self.agent._vprint(f"  {_get_cute_tool_message_impl('session_search', function_args, tool_duration, result=function_result)}")
            elif function_name == "memory":
                target = function_args.get("target", "memory")
                from tools.memory_tool import memory_tool as _memory_tool
                function_result = _memory_tool(
                    action=function_args.get("action"),
                    target=target,
                    content=function_args.get("content"),
                    old_text=function_args.get("old_text"),
                    store=self.agent._memory_store,
                )
                # Also send user observations to Honcho when active
                if self.agent._honcho and target == "user" and function_args.get("action") == "add":
                    self.agent._honcho_save_user_observation(function_args.get("content", ""))
                tool_duration = time.time() - tool_start_time
                if self.agent.quiet_mode:
                    self.agent._vprint(f"  {_get_cute_tool_message_impl('memory', function_args, tool_duration, result=function_result)}")
            elif function_name == "clarify":
                from tools.clarify_tool import clarify_tool as _clarify_tool
                function_result = _clarify_tool(
                    question=function_args.get("question", ""),
                    choices=function_args.get("choices"),
                    callback=self.agent.clarify_callback,
                )
                tool_duration = time.time() - tool_start_time
                if self.agent.quiet_mode:
                    self.agent._vprint(f"  {_get_cute_tool_message_impl('clarify', function_args, tool_duration, result=function_result)}")
            elif function_name == "delegate_task":
                from tools.delegate_tool import delegate_task as _delegate_task
                tasks_arg = function_args.get("tasks")
                if tasks_arg and isinstance(tasks_arg, list):
                    spinner_label = f"🔀 delegating {len(tasks_arg)} tasks"
                else:
                    goal_preview = (function_args.get("goal") or "")[:30]
                    spinner_label = f"🔀 {goal_preview}" if goal_preview else "🔀 delegating"
                spinner = None
                if self.agent.quiet_mode and not self.agent.tool_progress_callback:
                    face = random.choice(KawaiiSpinner.KAWAII_WAITING)
                    spinner = KawaiiSpinner(f"{face} {spinner_label}", spinner_type='dots', print_fn=self.agent._print_fn)
                    spinner.start()
                self.agent._delegate_spinner = spinner
                _delegate_result = None
                try:
                    function_result = _delegate_task(
                        goal=function_args.get("goal"),
                        context=function_args.get("context"),
                        toolsets=function_args.get("toolsets"),
                        tasks=tasks_arg,
                        max_iterations=function_args.get("max_iterations"),
                        parent_agent=self.agent,
                    )
                    _delegate_result = function_result
                finally:
                    self.agent._delegate_spinner = None
                    tool_duration = time.time() - tool_start_time
                    cute_msg = _get_cute_tool_message_impl('delegate_task', function_args, tool_duration, result=_delegate_result)
                    if spinner:
                        spinner.stop(cute_msg)
                    elif self.agent.quiet_mode:
                        self.agent._vprint(f"  {cute_msg}")
            elif self.agent.quiet_mode:
                spinner = None
                if not self.agent.tool_progress_callback:
                    face = random.choice(KawaiiSpinner.KAWAII_WAITING)
                    emoji = _get_tool_emoji(function_name)
                    preview = _build_tool_preview(function_name, function_args) or function_name
                    spinner = KawaiiSpinner(f"{face} {emoji} {preview}", spinner_type='dots', print_fn=self.agent._print_fn)
                    spinner.start()
                _spinner_result = None
                try:
                    function_result = handle_function_call(
                        function_name, function_args, effective_task_id,
                        enabled_tools=list(self.agent.valid_tool_names) if self.agent.valid_tool_names else None,
                        honcho_manager=self.agent._honcho,
                        honcho_session_key=self.agent._honcho_session_key,
                    )
                    _spinner_result = function_result
                except Exception as tool_error:
                    function_result = f"Error executing tool '{function_name}': {tool_error}"
                    logger.error("handle_function_call raised for %s: %s", function_name, tool_error, exc_info=True)
                finally:
                    tool_duration = time.time() - tool_start_time
                    cute_msg = _get_cute_tool_message_impl(function_name, function_args, tool_duration, result=_spinner_result)
                    if spinner:
                        spinner.stop(cute_msg)
                    else:
                        self.agent._vprint(f"  {cute_msg}")
            else:
                try:
                    function_result = handle_function_call(
                        function_name, function_args, effective_task_id,
                        enabled_tools=list(self.agent.valid_tool_names) if self.agent.valid_tool_names else None,
                        honcho_manager=self.agent._honcho,
                        honcho_session_key=self.agent._honcho_session_key,
                    )
                except Exception as tool_error:
                    function_result = f"Error executing tool '{function_name}': {tool_error}"
                    logger.error("handle_function_call raised for %s: %s", function_name, tool_error, exc_info=True)
                tool_duration = time.time() - tool_start_time

            result_preview = function_result if self.agent.verbose_logging else (
                function_result[:200] if len(function_result) > 200 else function_result
            )

            # Log tool errors to the persistent error log so [error] tags
            # in the UI always have a corresponding detailed entry on disk.
            _is_error_result, _ = _detect_tool_failure(function_name, function_result)
            if _is_error_result:
                logger.warning("Tool %s returned error (%.2fs): %s", function_name, tool_duration, result_preview)

            if self.agent.verbose_logging:
                logging.debug(f"Tool {function_name} completed in {tool_duration:.2f}s")
                logging.debug(f"Tool result ({len(function_result)} chars): {function_result}")

            # Guard against tools returning absurdly large content that would
            # blow up the context window. 100K chars ≈ 25K tokens — generous
            # enough for any reasonable tool output but prevents catastrophic
            # context explosions (e.g. accidental base64 image dumps).
            MAX_TOOL_RESULT_CHARS = 100_000
            if len(function_result) > MAX_TOOL_RESULT_CHARS:
                original_len = len(function_result)
                function_result = (
                    function_result[:MAX_TOOL_RESULT_CHARS]
                    + f"\n\n[Truncated: tool response was {original_len:,} chars, "
                    f"exceeding the {MAX_TOOL_RESULT_CHARS:,} char limit]"
                )

            tool_msg = {
                "role": "tool",
                "content": function_result,
                "tool_call_id": tool_call.id
            }
            messages.append(tool_msg)

            if not self.agent.quiet_mode:
                if self.agent.verbose_logging:
                    print(f"  ✅ Tool {i} completed in {tool_duration:.2f}s")
                    print(f"     Result: {function_result}")
                else:
                    response_preview = function_result[:self.agent.log_prefix_chars] + "..." if len(function_result) > self.agent.log_prefix_chars else function_result
                    print(f"  ✅ Tool {i} completed in {tool_duration:.2f}s - {response_preview}")

            if self.agent._interrupt_requested and i < len(assistant_message.tool_calls):
                remaining = len(assistant_message.tool_calls) - i
                self.agent._vprint(f"{self.agent.log_prefix}⚡ Interrupt: skipping {remaining} remaining tool call(s)", force=True)
                for skipped_tc in assistant_message.tool_calls[i:]:
                    skipped_name = skipped_tc.function.name
                    skip_msg = {
                        "role": "tool",
                        "content": f"[Tool execution skipped — {skipped_name} was not started. User sent a new message]",
                        "tool_call_id": skipped_tc.id
                    }
                    messages.append(skip_msg)
                break

            if self.agent.tool_delay > 0 and i < len(assistant_message.tool_calls):
                time.sleep(self.agent.tool_delay)

        # ── Budget pressure injection ─────────────────────────────────
        # After all tool calls in this turn are processed, check if we're
        # approaching max_iterations. If so, inject a warning into the LAST
        # tool result's JSON so the LLM sees it naturally when reading results.
        budget_warning = self.agent._get_budget_warning(api_call_count)
        if budget_warning and messages and messages[-1].get("role") == "tool":
            last_content = messages[-1]["content"]
            try:
                parsed = json.loads(last_content)
                if isinstance(parsed, dict):
                    parsed["_budget_warning"] = budget_warning
                    messages[-1]["content"] = json.dumps(parsed, ensure_ascii=False)
                else:
                    messages[-1]["content"] = last_content + f"\n\n{budget_warning}"
            except (json.JSONDecodeError, TypeError):
                messages[-1]["content"] = last_content + f"\n\n{budget_warning}"
            if not self.agent.quiet_mode:
                remaining = self.agent.max_iterations - api_call_count
                tier = "⚠️  WARNING" if remaining <= self.agent.max_iterations * 0.1 else "💡 CAUTION"
                print(f"{self.agent.log_prefix}{tier}: {remaining} iterations remaining")

    def execute(self, assistant_message, messages: list, effective_task_id: str, api_call_count: int = 0) -> None:
        """Execute tool calls from the assistant message and append results to messages.

        Dispatches to concurrent execution only for batches that look
        independent: read-only tools may always share the parallel path, while
        file reads/writes may do so only when their target paths do not overlap.
        """
        from run_agent import _should_parallelize_tool_batch
        tool_calls = assistant_message.tool_calls

        # Track which tools are about to run so cost attribution can
        # apportion the next API response's token delta across them.
        self.agent._current_turn_tool_names = [
            tc.function.name for tc in tool_calls
            if hasattr(tc, "function") and hasattr(tc.function, "name")
        ]

        # Allow _vprint during tool execution even with stream consumers
        self.agent._executing_tools = True
        try:
            if not _should_parallelize_tool_batch(tool_calls):
                return self.agent._execute_tool_calls_sequential(
                    assistant_message, messages, effective_task_id, api_call_count
                )

            return self.agent._execute_tool_calls_concurrent(
                assistant_message, messages, effective_task_id, api_call_count
            )
        finally:
            self.agent._executing_tools = False
