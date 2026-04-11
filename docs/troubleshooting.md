# Troubleshooting

Common errors and their fixes.

---

## Installation

### `ImportError: No module named 'hermes'`

```bash
pip install hermes-agent
# or from source:
pip install -e ".[dev]"
```

### `python-telegram-bot not found`

Install platform-specific extras:

```bash
pip install "hermes-agent[telegram]"
pip install "hermes-agent[discord]"
pip install "hermes-agent[slack]"
pip install "hermes-agent[all]"  # all platforms
```

---

## LLM / API Errors

### `AuthenticationError: No API key found`

Add your API key to `~/.hermes/.env`:

```bash
OPENROUTER_API_KEY=sk-or-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

### `RateLimitError` from the LLM provider

- You've exceeded the provider's rate limit.
- Switch to a provider with higher limits or use `smart_model_routing` to offload simple turns to a cheaper/faster model.
- OpenRouter automatically falls back across providers — use `provider: openrouter`.

### `Model not found`

Check the exact model ID for your provider:

```yaml
# OpenRouter models use the format: provider/model-name
model:
  default: "anthropic/claude-opus-4.6"
  # or
  default: "google/gemini-2.5-flash"
```

---

## Gateway

### `TELEGRAM_BOT_TOKEN not set` (or similar)

The gateway only starts adapters for which credentials are found. Add the missing env var to `~/.hermes/.env` and restart.

### Gateway starts but bot doesn't respond

1. Check gateway logs: `~/.hermes/logs/`
2. Verify the bot is correctly configured (see platform guides)
3. Test the LLM connection: run `hermes` interactively and send a message

### `Rate limit exceeded — please wait Xs`

A user hit the rate limit (default: 20 messages/minute). Increase if needed:

```bash
GATEWAY_RATE_LIMIT_PER_MINUTE=60
GATEWAY_RATE_LIMIT_BURST=10
```

Or disable: `GATEWAY_RATE_LIMIT_ENABLED=false`

### Messages from one user appearing in another user's session

This is a thread-local audit context leak. The fix is in `gateway/run.py` — ensure `clear_audit_context()` is called in the `finally` block of `_handle_message()`.

---

## Tools

### `Unknown tool: tool_name`

The tool is not registered. Common causes:

1. The toolset containing the tool is not enabled
2. A required dependency for the tool is missing
3. The env var for the tool's credentials is not set

Check which tools are available:
```
❯ what tools do you have?
```

### `Sandbox policy violation: path ... is not in allowed roots`

A tool tried to access a path outside the sandbox. Either:

1. The path is genuinely unsafe — review the tool call
2. The path is legitimate but not in the allowlist — add it:

```bash
# The sandbox checks these paths by default:
# - $HERMES_HOME (~/.hermes)
# - /tmp and /var/tmp
# - Current working directory
# - ~/Downloads, ~/Documents, ~/Desktop
```

To allow all paths (disable strict mode):

```bash
# Warn instead of block (default):
HERMES_SANDBOX_STRICT=0   # or unset

# Block violations:
HERMES_SANDBOX_STRICT=1
```

### `Schema validation error` on a tool call

The tool received arguments that don't match its schema. Check the tool's parameter requirements in the [Tool Reference](tools/index.md).

### Tool audit log

Every tool call is logged to `~/.hermes/logs/audit.jsonl`:

```bash
tail -f ~/.hermes/logs/audit.jsonl | python3 -m json.tool
```

---

## Memory & Skills

### `Learning rejected: quality score too low`

The memory entry or skill content didn't meet the quality threshold (default: 0.30).

To lower the threshold:

```bash
HERMES_LEARNING_MIN_QUALITY=0.1
```

Signs of low quality:
- Very short content (< 5 characters)
- Only vague words ("update", "changed", "fixed")
- Missing frontmatter in skill files

### `Memory limit reached for profile`

The profile has hit `HERMES_LEARNING_MAX_ENTRIES` (default: 100). Increase the limit or clear old entries.

### Rolling back a bad learning

Find the journal entry ID:

```bash
tail -20 ~/.hermes/logs/learning_journal.jsonl | python3 -m json.tool
```

Roll it back from the CLI or in code:

```python
from agent.learning_journal import rollback
result = rollback("entry-uuid-here")
print(result)
```

---

## Docker

### Container starts but can't reach external services

Check that `~/.hermes/.env` is mounted:

```bash
docker run -v ~/.hermes:/root/.hermes hermes-agent gateway
```

### `Permission denied` on `~/.hermes/`

The container user may not match the host user. Add `--user $(id -u):$(id -g)` or fix permissions:

```bash
chmod -R 755 ~/.hermes
```

---

## Performance

### Agent responses are slow

1. Check `tool_progress: verbose` in `cli-config.yaml` to see what's taking time
2. Use a faster/cheaper model for simple turns: enable `smart_model_routing`
3. Reduce `max_iterations` in `delegation` settings

### High memory usage

- Session trajectories accumulate in `~/.hermes/logs/` — delete old ones
- Reduce `HERMES_JOURNAL_MAX_ENTRIES` to keep the learning journal smaller

---

## Debug Mode

Enable verbose output:

```bash
hermes --verbose
# or in config:
display:
  tool_progress: verbose
```

Or toggle at runtime:

```
❯ /verbose
```

View session replay:

```bash
ls ~/.hermes/logs/session_*.json | tail -1 | xargs python3 -m json.tool | less
```
