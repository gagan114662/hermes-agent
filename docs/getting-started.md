# Getting Started

This guide walks you through installing Hermes, running the interactive CLI, and connecting your first messaging platform.

---

## Prerequisites

- Python 3.11+
- An LLM API key (OpenRouter, Anthropic, or any OpenAI-compatible endpoint)

---

## Installation

=== "pip"

    ```bash
    pip install hermes-agent
    ```

=== "uv (recommended)"

    ```bash
    uv pip install hermes-agent
    ```

=== "From source"

    ```bash
    git clone https://github.com/hermesai/hermes-agent
    cd hermes-agent
    pip install -e ".[dev]"
    ```

---

## First Run — Interactive CLI

```bash
hermes
```

On first launch Hermes creates `~/.hermes/` and asks for your LLM API key if none is set.

To set the key in advance:

```bash
echo "OPENROUTER_API_KEY=sk-or-..." >> ~/.hermes/.env
```

Then run `hermes` and you will get a chat prompt. Try:

```
❯ what tools do you have?
❯ remember that my business name is Acme Corp
❯ /skills
```

---

## Directory layout

Hermes keeps all its state in `~/.hermes/` (or `$HERMES_HOME` if set):

```
~/.hermes/
  .env            ← API keys and secrets (never committed)
  memories/       ← Persistent memory per profile
  skills/         ← Learned skills (markdown playbooks)
  logs/
    audit.jsonl          ← Tool invocation audit log
    learning_journal.jsonl ← Memory/skill change log
    session_*.json       ← Full session trajectories
  skins/          ← Custom CLI themes
```

---

## Setting Up the Messaging Gateway

The gateway connects Hermes to Telegram, Discord, Slack, and other platforms.

### 1. Add credentials to `~/.hermes/.env`

```bash
# Required: at least one messaging platform
TELEGRAM_BOT_TOKEN=7123456789:AAF...

# Optional: LLM API key (if not already set)
OPENROUTER_API_KEY=sk-or-...
```

### 2. Start the gateway

```bash
hermes gateway
```

The gateway starts all platforms for which credentials are found and prints which ones are active.

### 3. Send a message

Send a message to your bot on the configured platform. Hermes will respond.

---

## Configuration File

For more control, create `~/.hermes/cli-config.yaml` (or `cli-config.yaml` in your project):

```yaml
model:
  default: "anthropic/claude-opus-4.6"
  provider: "auto"

terminal:
  backend: "local"
  timeout: 180
```

See the full [Configuration Reference](configuration.md) for all options.

---

## Enabling Toolsets

Hermes loads toolsets based on which API keys are present. To manually control which toolsets are active, add to your config:

```yaml
# cli-config.yaml
toolsets:
  - crm
  - google-workspace
  - file
  - web
```

Or start with a specific toolset from the CLI:

```bash
hermes --toolset crm,file,web
```

---

## Next Steps

- [Configuration Reference](configuration.md) — tune every setting
- [Platform Guides](platforms/index.md) — connect Telegram, Discord, Slack, etc.
- [Tool Reference](tools/index.md) — explore all 130+ available tools
- [Troubleshooting](troubleshooting.md) — if something goes wrong
