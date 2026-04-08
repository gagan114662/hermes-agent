"""Tests for coordinator mode prompt."""
from agent.coordinator import get_coordinator_prompt_addition, COORDINATOR_SYSTEM_PROMPT


def test_coordinator_prompt_is_string():
    prompt = get_coordinator_prompt_addition()
    assert isinstance(prompt, str)
    assert len(prompt) > 100


def test_coordinator_prompt_mentions_spawn_fresh():
    prompt = COORDINATOR_SYSTEM_PROMPT
    assert "fresh" in prompt.lower()


def test_coordinator_prompt_mentions_continue():
    prompt = COORDINATOR_SYSTEM_PROMPT
    assert "continue" in prompt.lower()


def test_coordinator_prompt_mentions_parallel():
    prompt = get_coordinator_prompt_addition()
    assert "parallel" in prompt.lower() or "async" in prompt.lower()
