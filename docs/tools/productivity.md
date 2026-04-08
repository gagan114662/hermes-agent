# Productivity Tools

## File Tools (`file` toolset)

| Tool | Description |
|------|-------------|
| `read_file` | Read a file with line numbers, supports pagination |
| `write_file` | Write/overwrite a file |
| `patch` | Find-and-replace edits (safer than rewriting) |
| `search_files` | Grep-style search or find-by-name |

## Automation (`automation` toolset)

Schedule recurring tasks:

```
cron_create(schedule="0 9 * * 1-5", task="send daily standup summary to Telegram")
cron_list()
cron_delete(id="abc123")
```

## Delegation (`delegation` toolset)

Spawn parallel subagents:

```
delegate_task(tasks=[
  {"name": "research", "prompt": "Research competitor pricing"},
  {"name": "draft", "prompt": "Draft outreach email"},
])
```

## Memory (`memory` toolset)

Persist facts across sessions:

```
memory(action="save", content="Client Acme Corp uses Salesforce for their CRM")
memory(action="recall", query="what CRM does Acme use?")
```

## Second Brain (`second-brain` toolset)

Domain-specific knowledge vaults — see the [Tool Reference overview](index.md).

## Google Workspace (`google-workspace` toolset)

Requires OAuth setup. See credentials setup in [Getting Started](../getting-started.md).

| Tool | Description |
|------|-------------|
| `gmail_search` | Search Gmail |
| `gmail_send` | Send email |
| `gmail_reply` | Reply to a thread |
| `calendar_list` | List upcoming events |
| `calendar_create` | Create a calendar event |
| `sheets_get` | Read spreadsheet data |
| `sheets_append` | Append rows |
