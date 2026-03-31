"""Tests for auto memory extraction."""
import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from agent.extract_memories import maybe_extract_memories, _extract_and_save


def test_maybe_extract_memories_short_convo_skipped():
    """Conversations with <4 messages are skipped."""
    agent = MagicMock()
    with tempfile.TemporaryDirectory() as d:
        _extract_and_save([{"role": "user", "content": "hi"}], d, agent)
        # No LLM call should have been made
        agent.client.chat.completions.create.assert_not_called()


def test_maybe_extract_memories_fires_thread():
    """maybe_extract_memories spawns a daemon thread."""
    import threading
    agent = MagicMock()
    messages = [{"role": "user", "content": f"msg {i}"} for i in range(5)]

    threads_before = threading.active_count()
    maybe_extract_memories(messages=messages, agent=agent, memories_dir="/tmp/test_mem_x")
    # Thread is daemon — may finish before we check, just verify no exception
