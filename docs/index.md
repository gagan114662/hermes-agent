# Hermes Agent

**Hermes is a self-improving AI employee** that connects to your messaging platforms — Telegram, Discord, Slack, WhatsApp, Signal, Email, and more — and executes real work on your behalf.

It remembers context across sessions, learns new skills, and integrates with your business tools (CRM, calendar, invoicing, social media, booking, and more).

---

## What Hermes does

- **Runs as an AI employee** — answer customer messages, book appointments, send invoices, post social media content
- **Connects to 15+ platforms** — one agent, every channel
- **Self-improving** — learns skills from your feedback, remembers facts permanently
- **Tool-first** — 130+ built-in tools across 30+ toolsets, with MCP server support for unlimited extensions
- **Secure by design** — input sanitization, tool sandboxing, audit logs, rate limiting

## Quick Start

```bash
# Install
pip install hermes-agent

# Interactive CLI
hermes

# Messaging gateway (Telegram, Discord, Slack, etc.)
hermes gateway
```

See [Getting Started](getting-started.md) for the full setup walkthrough.

## Architecture

```
You / Your Customers
        │
        ▼
  ┌─────────────────────────────┐
  │   Messaging Gateway         │  ← Telegram, Discord, Slack, WhatsApp, ...
  │   gateway/run.py            │
  └──────────┬──────────────────┘
             │ MessageEvent
             ▼
  ┌─────────────────────────────┐
  │   Agent Loop                │  ← LLM + tool calling
  │   agent/run.py              │
  └──────────┬──────────────────┘
             │ tool call
             ▼
  ┌─────────────────────────────┐
  │   Tool Registry             │  ← 130+ tools, schema validation, sandbox, audit
  │   tools/registry.py         │
  └──────────┬──────────────────┘
             │
    ┌────────┴──────────┐
    ▼                   ▼
 External APIs     Local Storage
 (CRM, Email,      (Memory, Skills,
  Calendar, ...)    Journal, Logs)
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Skills** | Reusable procedural memory — markdown playbooks stored in `~/.hermes/skills/` |
| **Memory** | Persistent facts stored in `~/.hermes/memories/` per platform profile |
| **Toolsets** | Named groups of tools enabled per session or gateway platform |
| **Gateway** | Long-running process that bridges messaging platforms to the agent |
| **Learning Journal** | Append-only log of every memory/skill write with rollback support |

## Documentation sections

- [Getting Started](getting-started.md) — install, first run, .env setup
- [Configuration Reference](configuration.md) — every `cli-config.yaml` option
- [Tool Reference](tools/index.md) — all 130+ tools by category
- [Platform Guides](platforms/index.md) — per-platform setup for each messaging integration
- [Troubleshooting](troubleshooting.md) — common errors and fixes
