# Unix Philosophy Refactor — Design Doc

**Date:** 2026-04-11
**Author:** Gagan Arora
**Status:** Approved

---

## Overview

Two-PR approach to make Hermes Agent more composable and Unix-native.

- **PR 1** — OpenRouter + Nemotron config fix (unblocks Telegram today)
- **PR 2** — Unix philosophy refactor: pipe mode + agent-as-stdio-server + thin gateway

---

## PR 1: OpenRouter + Nemotron Fix

### Problem
`~/.hermes/config.yaml` is missing, so hermes falls back to no model. The Anthropic OAuth token is out of quota. The `.env` has a valid `OPENROUTER_API_KEY`.

### Solution
Create `~/.hermes/config.yaml` setting model to `nvidia/llama-3.3-nemotron-super-49b-v1` via OpenRouter. Restart gateway.

### Files Changed
- `~/.hermes/config.yaml` — created with model + provider
- Gateway restart via `hermes gateway run --replace`

### Success Criteria
- `curl http://localhost:8642/v1/chat/completions` with `hermes-local-dev` key returns a real response
- Telegram messages get replies

---

## PR 2: Unix Philosophy Refactor

### Problem
`hermes gateway run` is a 308KB monolith that imports `AIAgent` directly, manages 20+ platform sessions, and handles all platform I/O in one process. This violates the Unix principle of "do one thing well":

- Can't use hermes in shell pipelines (`cat logs | hermes "analyze"`)
- Adding a new platform requires understanding the full gateway internals
- Agent logic and message routing are tightly coupled

### Design Principles Applied
1. **Do One Thing Well** — gateway routes messages; agent processes them; they communicate via stdio pipes
2. **Universal Text Interface** — JSON-L over stdin/stdout as the lingua franca between processes
3. **Composability** — `cat file | hermes "prompt"` works from any shell script or cron job
4. **Everything is a File** — agent state/memory already uses flat files (MEMORY.md, USER.md) — preserved

### Architecture

#### Before
```
[Telegram] ──┐
[Discord]  ──┤
[Slack]    ──┤──> GatewayRunner ──> AIAgent (direct import)
[SMS]      ──┤         │
[...]      ──┘   SessionStore
```

#### After
```
[Telegram] ──┐
[Discord]  ──┤
[Slack]    ──┤──> GatewayRunner (thin) ──> stdin/stdout pipe ──> hermes agent serve
[SMS]      ──┤         │                        (per session)
[...]      ──┘   ProcessRegistry
                 (session → subprocess)
```

#### Pipe Mode (CLI)
```bash
# These all work after PR 2:
cat server.log | hermes "what errors should I fix?"
hermes "summarize" < long_report.md > summary.md
echo "translate to French: hello world" | hermes
```

### Components

#### 1. `agent/stdio_server.py` (new, ~150 lines)
Long-running process that reads JSON-L from stdin, writes JSON-L to stdout.

**Input format:**
```json
{"session_id": "tg-12345", "message": "hello", "platform": "telegram"}
```

**Output format (streaming):**
```json
{"session_id": "tg-12345", "delta": "Hello! How can I help?"}
{"session_id": "tg-12345", "done": true, "usage": {"turns": 1}}
```

**Started as:**
```bash
hermes agent serve --transport stdio
```

#### 2. Pipe mode in `cli.py` (~30 lines)
Detect `not sys.stdin.isatty()`. If true, read stdin as content, combine with positional arg as prompt, run single query, output JSON-L.

```python
if not sys.stdin.isatty():
    content = sys.stdin.read()
    prompt = f"{args.query}\n\n{content}" if args.query else content
    run_batch_query(prompt, json_output=True)
```

#### 3. `gateway/run.py` refactor (~80 lines changed)
Replace `AIAgent` direct instantiation with subprocess spawn:

```python
# Before
agent = AIAgent(config=..., tools=...)
response = await agent.run(message)

# After
proc = await self._get_or_spawn_agent_process(session_id)
await proc.stdin.write(json.dumps({"session_id": session_id, "message": message}) + "\n")
response = await self._read_until_done(proc.stdout, session_id)
```

`ProcessRegistry` manages `session_id → asyncio.subprocess.Process` mapping with cleanup on session expiry.

#### 4. `hermes_cli/commands.py` — register `agent serve` subcommand

### Files Changed
| File | Change | Lines |
|------|--------|-------|
| `agent/stdio_server.py` | New file — stdio JSON-L server | ~150 |
| `cli.py` | Pipe mode detection + batch JSON-L output | ~30 |
| `gateway/run.py` | Swap AIAgent import for subprocess spawn | ~80 |
| `gateway/process_registry.py` | New file — session→process map with cleanup | ~60 |
| `hermes_cli/commands.py` | Register `agent serve` subcommand | ~10 |

**Not changed:** platform adapters, tools, skills, memory plugins, auth — zero regression risk.

### Success Criteria
- `echo "hello" | hermes` returns a response on stdout
- `cat /var/log/syslog | hermes "any errors?"` works
- Telegram message routes through a subprocess (`ps aux | grep "hermes agent serve"` shows per-session processes)
- Existing `hermes chat` interactive mode unchanged
- All existing platform adapters work without modification

### Trade-offs & Risks
- **Process overhead:** Each session spawns a subprocess. Mitigated by keeping processes alive (not per-message spawn).
- **Startup latency:** First message per session has ~1s extra latency for process spawn. Subsequent messages instant.
- **IPC complexity:** JSON-L over stdio is simple but requires careful buffering. Use `asyncio.StreamReader` with `readline()`.
- **Session cleanup:** Processes must be reaped on session expiry. `ProcessRegistry` handles this with a TTL sweep.

---

## Implementation Order

1. PR 1: Config fix → merge → verify Telegram works
2. PR 2, step 1: `agent/stdio_server.py` + `agent serve` command
3. PR 2, step 2: Pipe mode in `cli.py`
4. PR 2, step 3: Gateway subprocess refactor
5. PR 2, step 4: Integration test all three together
