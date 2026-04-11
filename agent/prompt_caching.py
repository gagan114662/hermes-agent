"""Anthropic prompt caching (system_and_3 strategy).

Reduces input token costs by ~75% on multi-turn conversations by caching
the conversation prefix. Uses 4 cache_control breakpoints (Anthropic max):
  1. System prompt (stable across all turns)
  2-4. Last 3 non-system messages (rolling window)

Pure functions -- no class state, no AIAgent dependency.
"""

import copy
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CacheSafeParams:
    """Snapshot of parent agent's cached prompt prefix for forked subagents.

    Subagents that share these params avoid re-paying for the full system
    prompt and conversation prefix on every fork.
    """
    system_prompt: str
    # First N messages already cached by parent (the stable prefix)
    cached_messages_prefix: list[dict[str, Any]]
    # Indices in the original message list where cache_control was placed
    cache_breakpoint_indices: list[int]


# Thread-local storage so different sessions don't interfere
_cache_safe_params: CacheSafeParams | None = None
_cache_lock = threading.Lock()


def save_cache_safe_params(params: CacheSafeParams | None) -> None:
    """Save the current parent's cache params after each successful API call."""
    global _cache_safe_params
    with _cache_lock:
        _cache_safe_params = params


def get_last_cache_safe_params() -> CacheSafeParams | None:
    """Get the last saved cache params for use by forked subagents."""
    with _cache_lock:
        return _cache_safe_params


def _apply_cache_marker(msg: dict, cache_marker: dict, native_anthropic: bool = False) -> None:
    """Add cache_control to a single message, handling all format variations."""
    role = msg.get("role", "")
    content = msg.get("content")

    if role == "tool":
        if native_anthropic:
            msg["cache_control"] = cache_marker
        return

    if content is None or content == "":
        msg["cache_control"] = cache_marker
        return

    if isinstance(content, str):
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": cache_marker}
        ]
        return

    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = cache_marker


def apply_anthropic_cache_control(
    api_messages: List[Dict[str, Any]],
    cache_ttl: str = "5m",
    native_anthropic: bool = False,
) -> List[Dict[str, Any]]:
    """Apply system_and_3 caching strategy to messages for Anthropic models.

    Places up to 4 cache_control breakpoints: system prompt + last 3 non-system messages.

    When the system prompt contains DYNAMIC_BOUNDARY (the CC-style static/dynamic
    split), the system message is expanded into two content blocks — the static
    prefix gets cache_control and the dynamic suffix does not. This means memory
    updates and timestamp changes don't invalidate the static prefix cache.

    Returns:
        Deep copy of messages with cache_control breakpoints injected.
    """
    from agent.prompt_builder import DYNAMIC_BOUNDARY, split_static_dynamic

    messages = copy.deepcopy(api_messages)
    if not messages:
        return messages

    marker = {"type": "ephemeral"}
    if cache_ttl == "1h":
        marker["ttl"] = "1h"

    breakpoints_used = 0

    if messages[0].get("role") == "system":
        sys_content = messages[0].get("content", "")

        if isinstance(sys_content, str) and DYNAMIC_BOUNDARY in sys_content:
            # Split into static (cached) + dynamic (not cached) content blocks
            static_part, dynamic_part = split_static_dynamic(sys_content)
            blocks: List[Dict[str, Any]] = [
                {"type": "text", "text": static_part, "cache_control": marker},
            ]
            if dynamic_part:
                blocks.append({"type": "text", "text": dynamic_part})
            messages[0]["content"] = blocks
        else:
            # No boundary — cache the whole system prompt as before
            _apply_cache_marker(messages[0], marker, native_anthropic=native_anthropic)
        breakpoints_used += 1

    remaining = 4 - breakpoints_used
    non_sys = [i for i in range(len(messages)) if messages[i].get("role") != "system"]
    for idx in non_sys[-remaining:]:
        _apply_cache_marker(messages[idx], marker, native_anthropic=native_anthropic)

    return messages


def build_cache_safe_params(system_prompt: str, messages: list[dict[str, Any]]) -> CacheSafeParams:
    """Build CacheSafeParams from the current system prompt and messages.

    Identifies which messages have cache_control applied (the breakpoints)
    and extracts the prefix for subagent reuse.
    """
    breakpoints = []
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    breakpoints.append(i)
                    break
        elif isinstance(msg, dict) and "cache_control" in msg:
            breakpoints.append(i)

    # The prefix is everything up to and including the last breakpoint
    prefix_end = (max(breakpoints) + 1) if breakpoints else 0
    prefix = messages[:prefix_end]

    return CacheSafeParams(
        system_prompt=system_prompt,
        cached_messages_prefix=prefix,
        cache_breakpoint_indices=breakpoints,
    )
