# Configuration Reference

All settings live in `cli-config.yaml` (search order: `./cli-config.yaml` → `~/.hermes/cli-config.yaml`).

Copy the example and customize:

```bash
cp cli-config.yaml.example ~/.hermes/cli-config.yaml
```

Secrets (API keys, tokens, passwords) go in `~/.hermes/.env`, not in the config file.

---

## `model`

Controls which LLM is used.

```yaml
model:
  default: "anthropic/claude-opus-4.6"
  provider: "auto"
  # api_key: ""
  base_url: "https://openrouter.ai/api/v1"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default` | string | `anthropic/claude-opus-4.6` | Model ID. Overridden by `--model` flag or `HERMES_MODEL` env var. |
| `provider` | string | `auto` | Inference provider. See providers table below. |
| `api_key` | string | — | API key (falls back to `OPENROUTER_API_KEY` / provider-specific env var). |
| `base_url` | string | `https://openrouter.ai/api/v1` | Base URL for OpenAI-compatible endpoints. Required for `custom` / local providers. |

### Providers

| Value | Env var required | Notes |
|-------|-----------------|-------|
| `auto` | — | Detects from available credentials |
| `openrouter` | `OPENROUTER_API_KEY` | Default cloud provider |
| `nous` | — | Nous Portal OAuth (`hermes login`) |
| `nous-api` | `NOUS_API_KEY` | Nous Portal API key |
| `anthropic` | `ANTHROPIC_API_KEY` | Direct Anthropic API |
| `openai-codex` | — | OpenAI Codex (`hermes login --provider openai-codex`) |
| `copilot` | `GITHUB_TOKEN` | GitHub Copilot / GitHub Models |
| `zai` | `GLM_API_KEY` | z.ai / ZhipuAI GLM |
| `kimi-coding` | `KIMI_API_KEY` | Kimi / Moonshot AI |
| `minimax` | `MINIMAX_API_KEY` | MiniMax global |
| `minimax-cn` | `MINIMAX_CN_API_KEY` | MiniMax China |
| `huggingface` | `HF_TOKEN` | Hugging Face Inference |
| `kilocode` | `KILOCODE_API_KEY` | KiloCode gateway |
| `ai-gateway` | `AI_GATEWAY_API_KEY` | Vercel AI Gateway |
| `custom` | — | Any OpenAI-compatible endpoint. Set `base_url`. |
| `lmstudio` | — | Alias for `custom`, default port 1234 |
| `ollama` | — | Alias for `custom`, default port 11434 |
| `vllm` | — | Alias for `custom` |
| `llamacpp` | — | Alias for `custom` |

---

## `provider_routing`

OpenRouter-only. Controls how requests are routed across underlying providers.

```yaml
provider_routing:
  sort: "throughput"       # "price" | "throughput" | "latency"
  # only: ["anthropic", "google"]
  # ignore: ["deepinfra"]
  # order: ["anthropic", "google"]
  # require_parameters: true
  # data_collection: "deny"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `sort` | string | `price` | Sort strategy: `price`, `throughput`, or `latency`. |
| `only` | list | — | Whitelist of provider slugs. |
| `ignore` | list | — | Exclude these providers. |
| `order` | list | — | Try providers in this order (overrides load balancing). |
| `require_parameters` | bool | false | Require providers to support all request parameters. |
| `data_collection` | string | `allow` | `allow` or `deny` (excludes providers that may store data). |

---

## `smart_model_routing`

Use a cheaper model for short/simple turns.

```yaml
smart_model_routing:
  enabled: true
  max_simple_chars: 160
  max_simple_words: 28
  cheap_model:
    provider: openrouter
    model: google/gemini-2.5-flash
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | false | Enable smart routing. |
| `max_simple_chars` | int | 160 | Max chars for a "simple" turn. |
| `max_simple_words` | int | 28 | Max words for a "simple" turn. |
| `cheap_model.provider` | string | — | Provider for cheap model. |
| `cheap_model.model` | string | — | Model ID for cheap model. |

---

## `worktree`

```yaml
worktree: true
```

When `true`, each CLI session creates an isolated git worktree. Equivalent to always passing `--worktree` / `-w`. Default: `false`.

---

## `terminal`

Controls how shell commands are executed. Choose one backend.

### Local (default)

```yaml
terminal:
  backend: "local"
  cwd: "."
  timeout: 180
  lifetime_seconds: 300
  docker_mount_cwd_to_workspace: false
  # sudo_password: ""
```

### SSH

```yaml
terminal:
  backend: "ssh"
  cwd: "/home/user/project"
  timeout: 180
  lifetime_seconds: 300
  ssh_host: "my-server.example.com"
  ssh_user: "myuser"
  ssh_port: 22
  ssh_key: "~/.ssh/id_rsa"
```

### Docker

```yaml
terminal:
  backend: "docker"
  cwd: "/workspace"
  timeout: 180
  lifetime_seconds: 300
  docker_image: "nikolaik/python-nodejs:python3.11-nodejs20"
  docker_mount_cwd_to_workspace: true
  docker_forward_env:
    - "GITHUB_TOKEN"
    - "NPM_TOKEN"
```

### Singularity / Apptainer

```yaml
terminal:
  backend: "singularity"
  cwd: "/workspace"
  singularity_image: "docker://nikolaik/python-nodejs:python3.11-nodejs20"
```

### Modal

```yaml
terminal:
  backend: "modal"
  cwd: "/workspace"
  modal_image: "nikolaik/python-nodejs:python3.11-nodejs20"
```

### Daytona

```yaml
terminal:
  backend: "daytona"
  cwd: "~"
  daytona_image: "nikolaik/python-nodejs:python3.11-nodejs20"
  container_disk: 10240
```

### Common terminal keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `backend` | string | `local` | Execution backend. |
| `cwd` | string | `.` | Working directory (local) or path inside container/remote. |
| `timeout` | int | 180 | Command timeout in seconds. |
| `lifetime_seconds` | int | 300 | Session lifetime before auto-cleanup. |
| `container_cpu` | int | 1 | CPU cores (container backends). |
| `container_memory` | int | 5120 | Memory in MB (container backends). |
| `container_disk` | int | 51200 | Disk in MB (container backends). |
| `container_persistent` | bool | true | Persist filesystem across sessions. |
| `docker_mount_cwd_to_workspace` | bool | false | Mount launch cwd into `/workspace` (Docker). Security opt-in. |
| `sudo_password` | string | — | Enable sudo commands (piped via `sudo -S`). |

---

## `stt`

Voice transcription for messaging platforms.

```yaml
stt:
  enabled: true
  model: "whisper-1"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | true | Transcribe voice messages. |
| `model` | string | `whisper-1` | Whisper model: `whisper-1`, `gpt-4o-mini-transcribe`, `gpt-4o-transcribe`. |

Requires `OPENAI_API_KEY` in `.env`.

---

## `human_delay`

Add human-like pacing between message chunks on messaging platforms.

```yaml
human_delay:
  mode: "natural"    # "off" | "natural" | "custom"
  min_ms: 800
  max_ms: 2500
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `mode` | string | `off` | `off` disables delays, `natural` uses adaptive timing, `custom` uses min/max. |
| `min_ms` | int | 800 | Minimum delay in ms (custom mode). |
| `max_ms` | int | 2500 | Maximum delay in ms (custom mode). |

---

## `code_execution`

The `execute_code` tool sandbox.

```yaml
code_execution:
  timeout: 300
  max_tool_calls: 50
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `timeout` | int | 300 | Max seconds per script before kill. |
| `max_tool_calls` | int | 50 | Max RPC tool calls per execution. |

---

## `delegation`

Subagent delegation settings.

```yaml
delegation:
  max_iterations: 50
  default_toolsets: ["terminal", "file", "web"]
  # model: "google/gemini-3-flash-preview"
  # provider: "openrouter"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_iterations` | int | 50 | Max tool-calling turns per child agent. |
| `default_toolsets` | list | `["terminal","file","web"]` | Toolsets given to subagents. |
| `model` | string | — | Override model for subagents (empty = inherit parent). |
| `provider` | string | — | Override provider for subagents. |

---

## `mcp_servers`

MCP (Model Context Protocol) server definitions.

```yaml
mcp_servers:
  time:
    command: uvx
    args: ["mcp-server-time"]
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
  notion:
    url: https://mcp.notion.com/mcp
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_..."
```

Each server can be stdio-based (`command` + `args`) or SSE-based (`url`).

### MCP server sampling config

```yaml
mcp_servers:
  analysis:
    command: npx
    args: ["-y", "analysis-server"]
    sampling:
      enabled: true
      model: "gemini-3-flash"
      max_tokens_cap: 4096
      timeout: 30
      max_rpm: 10
      allowed_models: []
      max_tool_rounds: 5
      log_level: "info"
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `sampling.enabled` | bool | true | Allow server-initiated LLM requests. |
| `sampling.model` | string | — | Override model for sampling calls. |
| `sampling.max_tokens_cap` | int | — | Cap tokens per sampling request. |
| `sampling.timeout` | int | — | LLM call timeout in seconds. |
| `sampling.max_rpm` | int | — | Max requests per minute. |
| `sampling.allowed_models` | list | `[]` | Model whitelist (empty = all). |
| `sampling.max_tool_rounds` | int | — | Tool loop limit per sampling call. |
| `sampling.log_level` | string | `info` | Audit verbosity. |

---

## `display`

CLI appearance and behavior.

```yaml
display:
  compact: false
  tool_progress: all
  busy_input_mode: interrupt
  background_process_notifications: all
  bell_on_complete: false
  show_reasoning: false
  streaming: true
  skin: default
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `compact` | bool | false | Use compact banner mode. |
| `tool_progress` | string | `all` | `off` \| `new` \| `all` \| `verbose`. Controls tool activity display. |
| `busy_input_mode` | string | `interrupt` | What Enter does when agent is busy: `interrupt` or `queue`. |
| `background_process_notifications` | string | `all` | `off` \| `result` \| `error` \| `all`. Gateway background process verbosity. |
| `bell_on_complete` | bool | false | Terminal bell when agent finishes. |
| `show_reasoning` | bool | false | Show model thinking/reasoning. Toggle with `/reasoning show`. |
| `streaming` | bool | true | Stream tokens in real time. |
| `skin` | string | `default` | Visual theme. Built-ins: `default`, `ares`, `mono`, `slate`. |

### Custom skins

Drop a YAML file in `~/.hermes/skins/<name>.yaml`:

```yaml
name: my-theme
description: My custom theme
colors:
  banner_border: "#FFD700"
  banner_title: "#FFA500"
  banner_accent: "#FF8C00"
  banner_dim: "#808080"
  banner_text: "#FFFFFF"
  ui_accent: "#FFD700"
  response_border: "#FFA500"
spinner:
  waiting_faces: ["(●)", "(○)"]
  thinking_faces: ["(◑)", "(◐)"]
  thinking_verbs: ["thinking", "processing"]
branding:
  agent_name: "My Agent"
  welcome: "Hello! How can I help?"
  response_label: " ◆ My Agent "
  prompt_symbol: "◆ ❯ "
tool_prefix: "│"
```

---

## `privacy`

```yaml
privacy:
  redact_pii: false
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `redact_pii` | bool | false | Strip phone numbers and hash user/chat IDs before sending to LLM. |

---

## Environment Variables

Runtime overrides via `~/.hermes/.env` or shell environment:

| Variable | Description |
|----------|-------------|
| `HERMES_HOME` | Override `~/.hermes` directory |
| `HERMES_MODEL` | Override `model.default` |
| `HERMES_INFERENCE_PROVIDER` | Override `model.provider` |
| `HERMES_MAX_MESSAGE_LEN` | Max input message length (default: 32000) |
| `HERMES_SANDBOX_STRICT` | `1` = block sandbox violations (default: warn) |
| `HERMES_SANDBOX_BLOCK_NETWORK` | `1` = block all network calls from tools |
| `HERMES_LEARNING_MIN_QUALITY` | Minimum quality score for learning acceptance (default: 0.30) |
| `HERMES_LEARNING_MAX_ENTRIES` | Max memory entries per profile (default: 100) |
| `HERMES_SKILL_MAX_COUNT` | Max total skills (default: 500) |
| `HERMES_JOURNAL_MAX_ENTRIES` | Max learning journal lines (default: 500) |
| `GATEWAY_RATE_LIMIT_ENABLED` | `false` = disable rate limiting |
| `GATEWAY_RATE_LIMIT_PER_MINUTE` | Requests per minute per user (default: 20) |
| `GATEWAY_RATE_LIMIT_BURST` | Burst allowance (default: 5) |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `ANTHROPIC_API_KEY` | Anthropic direct API key |
| `OPENAI_API_KEY` | OpenAI API key |
