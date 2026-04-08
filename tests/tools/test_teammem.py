"""Tests for team memory namespace (target='team')."""
import json
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def team_file(tmp_path):
    """Fixture that patches TEAM_MEMORY_FILE to a temp path."""
    tf = str(tmp_path / "team.md")
    with patch("tools.memory_tool.TEAM_MEMORY_FILE", tf):
        yield tf


def _call_memory(action, target="team", content=None, old_text=None, store=None, team_file_path=None):
    """Helper to call memory_tool with TEAM_MEMORY_FILE patched."""
    import tools.memory_tool as mt
    if store is None:
        store = MagicMock()
    with patch("tools.memory_tool.TEAM_MEMORY_FILE", team_file_path):
        return json.loads(mt.memory_tool(
            action=action, target=target, content=content,
            old_text=old_text, store=store,
        ))


def test_team_write_creates_file(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    result = json.loads(mt.memory_tool(action="add", target="team", content="Use MEDDIC for qualification", store=store))
    assert result["success"] is True
    assert os.path.exists(team_file)


def test_team_write_content(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    mt.memory_tool(action="add", target="team", content="Deploy with blue-green strategy", store=store)
    with open(team_file) as f:
        contents = f.read()
    assert "Deploy with blue-green strategy" in contents


def test_team_read_returns_memories(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    mt.memory_tool(action="add", target="team", content="MEDDIC qualification", store=store)
    mt.memory_tool(action="add", target="team", content="Blue-green deploys", store=store)
    result = json.loads(mt.memory_tool(action="read", target="team", store=store))
    mems = result.get("memories", [])
    assert any("MEDDIC" in m for m in mems)
    assert any("Blue-green" in m for m in mems)


def test_team_read_empty_file(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    result = json.loads(mt.memory_tool(action="read", target="team", store=store))
    assert result.get("memories") == []


def test_team_read_nonexistent_file(tmp_path):
    import tools.memory_tool as mt
    nonexistent = str(tmp_path / "nosuchfile.md")
    store = MagicMock()
    with patch("tools.memory_tool.TEAM_MEMORY_FILE", nonexistent):
        result = json.loads(mt.memory_tool(action="read", target="team", store=store))
    assert result.get("memories") == []


def test_team_append_multiple(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    mt.memory_tool(action="add", target="team", content="Entry one", store=store)
    mt.memory_tool(action="add", target="team", content="Entry two", store=store)
    result = json.loads(mt.memory_tool(action="read", target="team", store=store))
    mems = result.get("memories", [])
    assert len(mems) == 2


def test_team_remove(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    mt.memory_tool(action="add", target="team", content="To be removed", store=store)
    mt.memory_tool(action="add", target="team", content="Keep this", store=store)
    result = json.loads(mt.memory_tool(action="remove", target="team", old_text="To be removed", store=store))
    assert result["success"] is True
    read = json.loads(mt.memory_tool(action="read", target="team", store=store))
    assert not any("To be removed" in m for m in read.get("memories", []))
    assert any("Keep this" in m for m in read.get("memories", []))


def test_team_replace(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    mt.memory_tool(action="add", target="team", content="Old guideline", store=store)
    result = json.loads(mt.memory_tool(action="replace", target="team", old_text="Old guideline", content="New guideline", store=store))
    assert result["success"] is True
    read = json.loads(mt.memory_tool(action="read", target="team", store=store))
    assert any("New guideline" in m for m in read.get("memories", []))
    assert not any("Old guideline" in m for m in read.get("memories", []))


def test_team_add_empty_content_rejected(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    result = json.loads(mt.memory_tool(action="add", target="team", content="", store=store))
    assert result["success"] is False


def test_team_add_none_content_rejected(team_file):
    import tools.memory_tool as mt
    store = MagicMock()
    result = json.loads(mt.memory_tool(action="add", target="team", content=None, store=store))
    assert result["success"] is False


def test_team_target_works_without_store():
    """team target should work even if store is None."""
    import tools.memory_tool as mt
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tf = os.path.join(tmpdir, "team.md")
        with patch("tools.memory_tool.TEAM_MEMORY_FILE", tf):
            result = json.loads(mt.memory_tool(action="add", target="team", content="Works", store=None))
        assert result["success"] is True


def test_TEAM_MEMORY_FILE_constant_exists():
    """TEAM_MEMORY_FILE constant is defined in memory_tool module."""
    from tools.memory_tool import TEAM_MEMORY_FILE
    assert isinstance(TEAM_MEMORY_FILE, str)
    assert "team.md" in TEAM_MEMORY_FILE
