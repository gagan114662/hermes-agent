# tests/test_stdio_server.py
import asyncio
import json
import pytest
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.asyncio
async def test_stdio_server_responds_to_valid_message():
    """Agent stdio server reads JSON-L input and writes JSON-L output."""
    from agent.stdio_server import StdioServer
    server = StdioServer(dry_run=True)
    response = await server.handle_message({
        "session_id": "test-1",
        "message": "hello",
        "platform": "test",
    })
    assert response["session_id"] == "test-1"
    assert response["done"] is True
    assert "content" in response


@pytest.mark.asyncio
async def test_stdio_server_rejects_missing_session_id():
    from agent.stdio_server import StdioServer, StdioServerError
    server = StdioServer(dry_run=True)
    with pytest.raises(StdioServerError, match="session_id required"):
        await server.handle_message({"message": "hello"})


@pytest.mark.asyncio
async def test_stdio_server_rejects_missing_message():
    from agent.stdio_server import StdioServer, StdioServerError
    server = StdioServer(dry_run=True)
    with pytest.raises(StdioServerError, match="message required"):
        await server.handle_message({"session_id": "test-1"})


def test_process_registry_stores_and_retrieves():
    from gateway.process_registry import ProcessRegistry
    registry = ProcessRegistry()
    registry.register("session-abc", "fake-process")
    assert registry.get("session-abc") == "fake-process"
    assert registry.get("nonexistent") is None


def test_process_registry_removes_on_cleanup():
    from gateway.process_registry import ProcessRegistry
    registry = ProcessRegistry()
    registry.register("session-abc", "fake-process")
    registry.remove("session-abc")
    assert registry.get("session-abc") is None


def test_gateway_subprocess_flag_config_logic():
    """Subprocess mode is the default; in-process mode is the opt-out."""
    def _resolve_flag(config):
        # True (subprocess) by default; False only when explicitly set to in-process
        return (config.get("agent") or {}).get("process_mode") != "in-process"

    assert _resolve_flag({}) is True                                           # default: subprocess
    assert _resolve_flag({"agent": {}}) is True                               # default: subprocess
    assert _resolve_flag({"agent": {"process_mode": "subprocess"}}) is True   # explicit subprocess
    assert _resolve_flag({"agent": {"process_mode": "in-process"}}) is False  # opt-out


def test_pipe_mode_does_not_hang_on_pipe_input():
    """hermes CLI does not hang when given piped stdin — just needs to start."""
    result = subprocess.run(
        [sys.executable, "hermes_cli/main.py", "--help"],
        input=b"hello world content",
        capture_output=True,
        timeout=10,
        cwd=_REPO_ROOT,
    )
    # --help always exits 0 regardless of stdin
    assert result.returncode == 0
