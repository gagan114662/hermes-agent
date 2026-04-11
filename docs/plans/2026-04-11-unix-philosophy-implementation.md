# Unix Philosophy Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore Telegram via OpenRouter/Nemotron (PR 1) and make Hermes composable via pipe mode + stdio agent server + thin gateway (PR 2).

**Architecture:** PR 1 is a config-only fix. PR 2 introduces `hermes agent serve --transport stdio` as a long-running JSON-L subprocess, refactors the gateway to spawn one process per session, and adds stdin pipe detection to the CLI.

**Tech Stack:** Python 3.11, asyncio, JSON-L over stdio, OpenRouter API, existing hermes_cli config/auth stack.

---

## PR 1: OpenRouter + Nemotron Config Fix

### Task 1: Update config.yaml and verify gateway responds

**Files:**
- Modify: `~/.hermes/config.yaml`
- Modify: `~/.hermes/.env` (verify OPENROUTER_API_KEY present)

**Step 1: Write ~/.hermes/config.yaml**

```yaml
model:
  default: nvidia/llama-3.3-nemotron-super-49b-v1
  provider: openrouter
```

**Step 2: Confirm OPENROUTER_API_KEY is in ~/.hermes/.env**

Run: `grep OPENROUTER_API_KEY ~/.hermes/.env`
Expected: `OPENROUTER_API_KEY=sk-or-v1-...`

**Step 3: Kill old gateway and restart**

```bash
pkill -f "hermes gateway" 2>/dev/null; sleep 2
cd ~/Desktop/my\ projects/hermes/hermes-agent
source .venv/bin/activate
set -a; source ~/.hermes/.env; set +a
hermes gateway run --replace &
sleep 4
```

**Step 4: Verify with curl**

```bash
curl -s http://localhost:8642/v1/chat/completions \
  -H "Authorization: Bearer hermes-local-dev" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"say hello in 5 words"}],"max_tokens":50}'
```

Expected: JSON response with `choices[0].message.content` containing actual text (not an error).

**Step 5: Send a Telegram message and confirm reply**

Send any message to your Telegram bot. Expected: reply within 10s.

**Step 6: Commit config to repo (not ~/.hermes — commit a documented example)**

```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
cat > docs/config-examples/openrouter-nemotron.yaml << 'EOF'
# Example: Free OpenRouter model (Nemotron)
model:
  default: nvidia/llama-3.3-nemotron-super-49b-v1
  provider: openrouter
EOF
git add docs/config-examples/openrouter-nemotron.yaml
git commit -m "docs: add OpenRouter nemotron config example"
```

---

## PR 2: Unix Philosophy Refactor

### Task 2: Write failing tests for stdio server

**Files:**
- Create: `tests/test_stdio_server.py`

**Step 1: Write the failing tests**

```python
# tests/test_stdio_server.py
import asyncio
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


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
```

**Step 2: Run tests to confirm they fail**

```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
source .venv/bin/activate
pip install pytest pytest-asyncio -q
pytest tests/test_stdio_server.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'agent.stdio_server'`

**Step 3: Commit failing tests**

```bash
git add tests/test_stdio_server.py
git commit -m "test: add failing tests for stdio server and process registry"
```

---

### Task 3: Implement ProcessRegistry

**Files:**
- Create: `gateway/process_registry.py`

**Step 1: Write the implementation**

```python
# gateway/process_registry.py
"""
ProcessRegistry — maps session IDs to live agent subprocess handles.

Each active session gets one long-running `hermes agent serve --transport stdio`
subprocess. The registry keeps them alive between messages so session memory
is preserved, and reaps them on expiry or explicit removal.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProcessEntry:
    process: asyncio.subprocess.Process
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)


class ProcessRegistry:
    """Thread-safe (asyncio) registry of session_id → subprocess."""

    def __init__(self, ttl_seconds: int = 3600):
        self._entries: Dict[str, ProcessEntry] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    def register(self, session_id: str, process) -> None:
        self._entries[session_id] = ProcessEntry(process=process)

    def get(self, session_id: str) -> Optional[asyncio.subprocess.Process]:
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        entry.last_used = time.monotonic()
        return entry.process

    def remove(self, session_id: str) -> None:
        self._entries.pop(session_id, None)

    async def spawn(self, session_id: str, hermes_bin: str = "hermes") -> asyncio.subprocess.Process:
        """Spawn a new agent serve process for this session."""
        async with self._lock:
            existing = self.get(session_id)
            if existing and existing.returncode is None:
                return existing

            proc = await asyncio.create_subprocess_exec(
                hermes_bin, "agent", "serve", "--transport", "stdio",
                "--session-id", session_id,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.register(session_id, proc)
            logger.info("Spawned agent process pid=%d for session=%s", proc.pid, session_id)
            return proc

    async def sweep_expired(self) -> int:
        """Reap processes idle longer than TTL. Returns count reaped."""
        now = time.monotonic()
        expired = [
            sid for sid, entry in self._entries.items()
            if now - entry.last_used > self._ttl
        ]
        for sid in expired:
            proc = self._entries[sid].process
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
            self.remove(sid)
            logger.info("Reaped expired agent process for session=%s", sid)
        return len(expired)
```

**Step 2: Run process registry tests**

```bash
pytest tests/test_stdio_server.py::test_process_registry_stores_and_retrieves \
       tests/test_stdio_server.py::test_process_registry_removes_on_cleanup -v
```

Expected: both PASS.

**Step 3: Commit**

```bash
git add gateway/process_registry.py
git commit -m "feat: add ProcessRegistry for session→subprocess mapping"
```

---

### Task 4: Implement StdioServer

**Files:**
- Create: `agent/stdio_server.py`

**Step 1: Write the implementation**

```python
# agent/stdio_server.py
"""
StdioServer — runs the Hermes agent as a long-running JSON-L stdio process.

Protocol:
  stdin  (one JSON object per line):
    {"session_id": "x", "message": "hello", "platform": "telegram"}

  stdout (one JSON object per line, streaming deltas then done):
    {"session_id": "x", "delta": "Hello! "}
    {"session_id": "x", "delta": "How can I help?"}
    {"session_id": "x", "done": true, "content": "Hello! How can I help?", "usage": {}}

  stderr: debug/error logs only (never parsed by gateway)

Usage:
  hermes agent serve --transport stdio [--session-id SESSION_ID]
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StdioServerError(Exception):
    pass


class StdioServer:
    """
    Handles JSON-L messages from stdin and writes JSON-L responses to stdout.

    dry_run=True skips actual LLM calls — used in tests.
    """

    def __init__(self, session_id: Optional[str] = None, dry_run: bool = False):
        self.session_id = session_id
        self.dry_run = dry_run
        self._agent = None  # lazy-init real AIAgent when not dry_run

    async def handle_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process one message, return final response dict."""
        session_id = payload.get("session_id", "").strip()
        message = payload.get("message", "").strip()

        if not session_id:
            raise StdioServerError("session_id required")
        if not message:
            raise StdioServerError("message required")

        if self.dry_run:
            return {
                "session_id": session_id,
                "done": True,
                "content": f"[dry-run echo] {message}",
                "usage": {},
            }

        # Real agent execution
        agent = await self._get_agent()
        content = await agent.run(message)
        return {
            "session_id": session_id,
            "done": True,
            "content": content,
            "usage": {},
        }

    async def _get_agent(self):
        if self._agent is None:
            # Import here to avoid slow startup in dry_run / test mode
            from run_agent import create_agent
            self._agent = await create_agent(session_id=self.session_id)
        return self._agent

    async def run_forever(self) -> None:
        """Main loop: read JSON-L from stdin, write JSON-L to stdout."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.BaseProtocol, sys.stdout.buffer
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

        logger.debug("StdioServer ready, waiting for input")

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break  # EOF — gateway closed the pipe

                line = line.decode().strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as e:
                    err = json.dumps({"error": f"invalid JSON: {e}"}) + "\n"
                    writer.write(err.encode())
                    await writer.drain()
                    continue

                try:
                    response = await self.handle_message(payload)
                except StdioServerError as e:
                    response = {
                        "session_id": payload.get("session_id", ""),
                        "error": str(e),
                        "done": True,
                    }

                out = json.dumps(response) + "\n"
                writer.write(out.encode())
                await writer.drain()

            except (BrokenPipeError, ConnectionResetError):
                break
            except Exception as e:
                logger.exception("Unhandled error in StdioServer loop: %s", e)


async def main(session_id: Optional[str] = None) -> None:
    server = StdioServer(session_id=session_id)
    await server.run_forever()
```

**Step 2: Run stdio server tests**

```bash
pytest tests/test_stdio_server.py::test_stdio_server_responds_to_valid_message \
       tests/test_stdio_server.py::test_stdio_server_rejects_missing_session_id \
       tests/test_stdio_server.py::test_stdio_server_rejects_missing_message -v
```

Expected: all three PASS.

**Step 3: Commit**

```bash
git add agent/stdio_server.py
git commit -m "feat: add StdioServer for JSON-L stdio agent protocol"
```

---

### Task 5: Register `agent serve` CLI subcommand

**Files:**
- Modify: `hermes_cli/commands.py` (find the subcommand registration block)
- Modify: `cli.py` (find where subcommands are dispatched)

**Step 1: Find where gateway subcommand is registered**

```bash
grep -n "gateway.*run\|add_subparser\|subcommand" \
  ~/Desktop/my\ projects/hermes/hermes-agent/hermes_cli/commands.py | head -20
grep -n "def.*gateway\|gateway.*subcommand" \
  ~/Desktop/my\ projects/hermes/hermes-agent/cli.py | head -10
```

**Step 2: Add agent serve subcommand**

In `cli.py`, find the block that handles `hermes gateway run` and add alongside it:

```python
elif args.command == "agent" and getattr(args, "agent_command", None) == "serve":
    transport = getattr(args, "transport", "stdio")
    session_id = getattr(args, "session_id", None)
    if transport == "stdio":
        import asyncio
        from agent.stdio_server import main as stdio_main
        asyncio.run(stdio_main(session_id=session_id))
    else:
        print(f"Unknown transport: {transport}", file=sys.stderr)
        sys.exit(1)
```

In `hermes_cli/commands.py`, register the subparser (find where `gateway` parser is added and add after):

```python
# agent serve subcommand
agent_parser = subparsers.add_parser("agent", help="Agent process management")
agent_subparsers = agent_parser.add_subparsers(dest="agent_command")
serve_parser = agent_subparsers.add_parser("serve", help="Run agent as a stdio/http server")
serve_parser.add_argument("--transport", default="stdio", choices=["stdio"], help="Transport protocol")
serve_parser.add_argument("--session-id", default=None, help="Session ID for this agent process")
```

**Step 3: Smoke test**

```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
source .venv/bin/activate
echo '{"session_id":"test","message":"hello"}' | hermes agent serve --transport stdio
```

Expected: `{"session_id": "test", "done": true, "content": "...actual LLM response..."}` printed to stdout.

**Step 4: Commit**

```bash
git add cli.py hermes_cli/commands.py
git commit -m "feat: register 'hermes agent serve --transport stdio' subcommand"
```

---

### Task 6: Add pipe mode to CLI

**Files:**
- Modify: `cli.py` — find the main entry point / argument parsing block

**Step 1: Find the right location**

```bash
grep -n "isatty\|stdin\|batch\|def main\|argparse" \
  ~/Desktop/my\ projects/hermes/hermes-agent/cli.py | head -20
```

**Step 2: Add pipe detection**

Find where `cli.py` handles the `-q`/`--query` batch mode (search for `run_batch` or `single_query`). Right before or after that block, add:

```python
# Pipe mode: stdin is not a TTY (e.g. cat file | hermes "prompt")
if not sys.stdin.isatty():
    piped_content = sys.stdin.read().strip()
    if piped_content:
        # Combine positional prompt with piped content
        prompt = args.query if getattr(args, "query", None) else ""
        full_input = f"{prompt}\n\n{piped_content}".strip() if prompt else piped_content
        # Reuse existing batch/single-query path
        args.query = full_input
        # Fall through to existing batch execution
```

**Step 3: Write a test for pipe mode**

```python
# Add to tests/test_stdio_server.py
import subprocess

def test_pipe_mode_reads_stdin():
    """hermes reads from stdin when not a TTY."""
    result = subprocess.run(
        ["python", "cli.py", "--dry-run", "what is this?"],
        input=b"hello world content",
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    # Should not hang or error — dry-run mode just echoes
    assert result.returncode == 0 or b"dry" in result.stdout.lower()
```

**Step 4: Run test**

```bash
pytest tests/test_stdio_server.py::test_pipe_mode_reads_stdin -v
```

**Step 5: Manual smoke test**

```bash
echo "What does this mean?" | hermes "explain"
cat ~/.hermes/gateway.log | hermes "any errors in the last 10 lines?"
```

Expected: real LLM response printed to stdout.

**Step 6: Commit**

```bash
git add cli.py tests/test_stdio_server.py
git commit -m "feat: add pipe mode — stdin content piped into query when not a TTY"
```

---

### Task 7: Refactor gateway to use ProcessRegistry (thin gateway)

**Files:**
- Modify: `gateway/run.py` — find `_handle_message_with_agent` and `_handle_message`

**Step 1: Find the agent instantiation site**

```bash
grep -n "AIAgent\|create_agent\|_handle_message_with_agent" \
  ~/Desktop/my\ projects/hermes/hermes-agent/gateway/run.py | head -20
```

**Step 2: Add ProcessRegistry to GatewayRunner.__init__**

Find `GatewayRunner.__init__` and add:

```python
from gateway.process_registry import ProcessRegistry
# ... inside __init__:
self._process_registry = ProcessRegistry(ttl_seconds=3600)
```

**Step 3: Replace direct AIAgent use with subprocess call**

Find `_handle_message_with_agent` (around line 2212). Replace the agent instantiation + run block with:

```python
async def _dispatch_to_agent_process(
    self, session_id: str, message: str, platform: str
) -> str:
    """Send message to per-session stdio agent subprocess, return response."""
    import json
    proc = await self._process_registry.spawn(session_id)

    payload = json.dumps({
        "session_id": session_id,
        "message": message,
        "platform": platform,
    }) + "\n"

    proc.stdin.write(payload.encode())
    await proc.stdin.drain()

    # Read until we get a line with "done": true
    full_content = ""
    while True:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=120.0)
        if not line:
            break
        response = json.loads(line.decode().strip())
        if "delta" in response:
            full_content += response["delta"]
        if response.get("done"):
            full_content = response.get("content", full_content)
            break

    return full_content
```

Then in `_handle_message_with_agent`, replace the agent run call with:
```python
response = await self._dispatch_to_agent_process(session_id, message, platform)
```

**Step 4: Add TTL sweep to gateway background tasks**

Find where background tasks are started in `GatewayRunner` (search for `asyncio.create_task` or `_start_background`). Add:

```python
asyncio.create_task(self._sweep_agent_processes())

async def _sweep_agent_processes(self):
    """Periodically reap idle agent processes."""
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        reaped = await self._process_registry.sweep_expired()
        if reaped:
            logger.info("Swept %d expired agent processes", reaped)
```

**Step 5: Test end-to-end**

```bash
# Restart gateway
pkill -f "hermes gateway"; sleep 2
hermes gateway run --replace &
sleep 5

# Send a test message via curl
curl -s http://localhost:8642/v1/chat/completions \
  -H "Authorization: Bearer hermes-local-dev" \
  -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"hello"}],"max_tokens":50}'

# Verify subprocess exists
ps aux | grep "hermes agent serve"
```

Expected: curl returns a real response AND `ps` shows at least one `hermes agent serve --transport stdio` process.

**Step 6: Commit**

```bash
git add gateway/run.py gateway/process_registry.py
git commit -m "feat: gateway dispatches to per-session stdio agent subprocesses

Replaces direct AIAgent import with ProcessRegistry that spawns
'hermes agent serve --transport stdio' per session. Gateway becomes
a thin process orchestrator; agent is now a composable Unix tool."
```

---

### Task 8: Create PRs

**Step 1: PR 1 — OpenRouter config fix**

```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
git checkout -b fix/openrouter-nemotron-config
# cherry-pick or recreate the config example commit
git push origin fix/openrouter-nemotron-config
gh pr create \
  --title "fix: switch default model to OpenRouter nemotron (restores Telegram)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `docs/config-examples/openrouter-nemotron.yaml` showing correct config
- Root cause: `~/.hermes/config.yaml` was missing, falling back to no model; Anthropic OAuth token was out of quota
- Fix: set `model.provider: openrouter` + `model.default: nvidia/llama-3.3-nemotron-super-49b-v1`

## Test plan
- [ ] `curl http://localhost:8642/v1/chat/completions` returns real text response
- [ ] Telegram bot replies to messages
EOF
)"
```

**Step 2: PR 2 — Unix philosophy refactor**

```bash
git checkout -b feat/unix-philosophy-refactor
git push origin feat/unix-philosophy-refactor
gh pr create \
  --title "feat: Unix philosophy refactor — pipe mode + stdio agent server + thin gateway" \
  --body "$(cat <<'EOF'
## Summary
- `hermes agent serve --transport stdio`: long-running JSON-L stdio server, one process per gateway session
- Pipe mode in CLI: `cat file | hermes "prompt"` works naturally
- Gateway refactored to use `ProcessRegistry` — spawns agent subprocesses per session instead of direct import
- Gateway becomes a thin process orchestrator; agent becomes a composable Unix tool

## Architecture change
Before: `GatewayRunner → AIAgent (direct import, same process)`
After:  `GatewayRunner → ProcessRegistry → hermes agent serve (subprocess per session)`

## Test plan
- [ ] `echo "hello" | hermes` returns response
- [ ] `cat /var/log/syslog | hermes "any errors?"` works
- [ ] `ps aux | grep "hermes agent serve"` shows per-session subprocesses after Telegram message
- [ ] All existing platform adapters (Telegram, SMS) still work
- [ ] `pytest tests/test_stdio_server.py` passes
EOF
)"
```

---

## Quick Reference

**Run all new tests:**
```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
source .venv/bin/activate
pytest tests/test_stdio_server.py -v
```

**Restart gateway after any change:**
```bash
pkill -f "hermes gateway"; sleep 2
cd ~/Desktop/my\ projects/hermes/hermes-agent && source .venv/bin/activate
set -a; source ~/.hermes/.env; set +a
hermes gateway run --replace &
```

**Watch gateway logs:**
```bash
tail -f ~/.hermes/gateway.log
```
