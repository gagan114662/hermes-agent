# Tool Reference

Hermes ships with 130+ built-in tools across 30+ toolsets. Tools are auto-registered at startup based on which credentials are available.

---

## Enabling toolsets

Tools are grouped into toolsets. Pass `--toolset` to enable specific groups:

```bash
hermes --toolset crm,file,web,google-workspace
```

Or configure defaults in `cli-config.yaml`:

```yaml
toolsets:
  - crm
  - file
  - web
  - google-workspace
```

---

## All toolsets and tools

### `crm` — CRM & Sales (34 tools)

Business CRM, outreach, project management, and knowledge wiki.

| Tool | Description |
|------|-------------|
| `crm_save` | Add or update a contact in the CRM |
| `crm_find` | Search contacts by name, phone, email, or status |
| `crm_log` | Log an interaction (call, SMS, email, meeting, DM) |
| `crm_deal` | Add or update a deal for a contact |
| `discovery_run` | Run structured discovery to find the real problem |
| `discovery_read` | Read the discovery document for a client |
| `scope_create` | Generate a Statement of Work |
| `scope_read` | Read the Statement of Work for a client |
| `scope_check` | Check if a request is in/out of scope |
| `prd_generate` | Generate a Product Requirement Document |
| `prd_read` | Read the PRD for a client |
| `project_create` | Create a project with phases and daily tasks |
| `project_list` | List all tasks for a client project |
| `project_update` | Update task status |
| `project_standup` | Run the daily standup for a project |
| `project_milestone_check` | Check if project is on track |
| `feedback_log` | Log a client feedback item (bug/change request) |
| `feedback_list` | List open and resolved feedback items |
| `feedback_resolve` | Mark a feedback item resolved |
| `outreach_draft` | Write a personalized cold outreach email |
| `outreach_send` | Send an outreach email (with tracking) |
| `outreach_sequence` | Send initial email + schedule follow-ups |
| `prospect_add` | Add a prospect to the outbound pipeline |
| `prospect_list` | List prospects filtered by status |
| `prospect_search` | Find prospects matching a natural language description |
| `prospect_enrich` | Visit LinkedIn/website and extract rich data |
| `prospect_update` | Update prospect status and notes |
| `prospect_digest` | Generate a Telegram-ready numbered digest of new prospects |
| `email_finder` | Find or guess a professional email address |
| `wiki_ingest` | Bulk ingest a long document into the business wiki |
| `wiki_query` | Ask the business wiki a question |
| `wiki_update` | Feed new information into the wiki |
| `wiki_read` | Read a full wiki page |
| `wiki_list` | List all wiki pages |

---

### `file` — File Operations (4 tools)

```yaml
toolsets: [file]
```

| Tool | Description |
|------|-------------|
| `read_file` | Read a text file with line numbers and pagination |
| `write_file` | Write content to a file (full replace) |
| `patch` | Targeted find-and-replace edits in files |
| `search_files` | Search file contents or find files by name |

---

### `terminal` — Shell Execution (2 tools)

```yaml
toolsets: [terminal]
```

| Tool | Description |
|------|-------------|
| `terminal` | Execute shell commands (persistent session) |
| `process` | Manage background processes |

---

### `web` — Web Search & Extraction (2 tools)

```yaml
toolsets: [web]
```

| Tool | Description |
|------|-------------|
| `web_search` | Search the web (up to 5 results) |
| `web_extract` | Extract content from a URL as markdown |

---

### `browser` — Headless Browser (13 tools)

Full Playwright-based browser control.

```yaml
toolsets: [browser]
```

| Tool | Description |
|------|-------------|
| `browser_navigate` | Navigate to a URL |
| `browser_snapshot` | Get accessibility tree snapshot with `@ref` IDs |
| `browser_click` | Click an element by `@ref` ID |
| `browser_type` | Type text into an input |
| `browser_press` | Press a keyboard key |
| `browser_scroll` | Scroll the page |
| `browser_back` | Navigate back |
| `browser_console` | Get console output and JS errors |
| `browser_vision` | Screenshot + vision AI analysis |
| `browser_upload_file` | Upload a file to an `<input type="file">` |
| `browser_save_image` | Save an image from the page to disk |
| `browser_get_images` | List all images on the page |
| `browser_close` | Close the browser session |

---

### `google-workspace` — Google Suite (8 tools)

Requires: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` + OAuth flow.

| Tool | Description |
|------|-------------|
| `gmail_search` | Search Gmail (Gmail search syntax) |
| `gmail_get` | Get full content of a Gmail message |
| `gmail_send` | Send a new email |
| `gmail_reply` | Reply to a Gmail thread |
| `calendar_list` | List upcoming calendar events |
| `calendar_create` | Create a calendar event |
| `sheets_get` | Read data from a Google Sheet range |
| `sheets_append` | Append rows to a Google Sheet |

---

### `messaging` — Cross-Platform Messaging (3 tools)

| Tool | Description |
|------|-------------|
| `send_message` | Send a message to a connected platform |
| `sms_send` | Send SMS via Twilio |
| `whatsapp_send` | Send WhatsApp via Twilio WhatsApp Business API |

---

### `booking` — Cal.com Appointments (5 tools)

Requires: `CALCOM_API_KEY`.

| Tool | Description |
|------|-------------|
| `booking_create_link` | Get a shareable booking link |
| `booking_list_slots` | List available slots on a date |
| `booking_list_upcoming` | List upcoming confirmed bookings |
| `booking_reschedule` | Reschedule a booking |
| `booking_cancel` | Cancel a booking |

---

### `easy-appointments` — Self-Hosted Booking (6 tools)

Requires: `EASYAPP_URL`, `EASYAPP_API_KEY`.

| Tool | Description |
|------|-------------|
| `easyapp_list_services` | List bookable services |
| `easyapp_list_providers` | List staff/providers |
| `easyapp_get_availability` | Get available slots |
| `easyapp_create_appointment` | Book an appointment |
| `easyapp_list_appointments` | List upcoming appointments |
| `easyapp_cancel_appointment` | Cancel an appointment |

---

### `invoicing` — Invoicing & Payments (5 tools)

Requires: `INVOICE_NINJA_URL`, `INVOICE_NINJA_API_KEY`.

| Tool | Description |
|------|-------------|
| `estimate_create` | Create a quote/estimate |
| `invoice_create` | Create an invoice |
| `invoice_list` | List invoices by status |
| `invoice_send` | Email an invoice |
| `payment_record` | Record a received payment |

---

### `email-marketing` — Mautic Email (7 tools)

Requires: `MAUTIC_URL`, `MAUTIC_USERNAME`, `MAUTIC_PASSWORD`.

| Tool | Description |
|------|-------------|
| `email_contact_add` | Add/update a Mautic contact |
| `email_segment_add_contact` | Add contact to a segment |
| `email_list_campaigns` | List drip campaigns |
| `email_campaign_send` | Enroll contacts into a campaign |
| `email_list_emails` | List email templates and broadcasts |
| `email_broadcast_send` | Send a one-time broadcast |
| `email_stats` | Get open/click/send stats |

---

### `social_media` — Buffer (4 tools)

Requires: `BUFFER_CLIENT_ID`, `BUFFER_CLIENT_SECRET`, `BUFFER_ACCESS_TOKEN`.

| Tool | Description |
|------|-------------|
| `social_profiles` | List connected social profiles |
| `social_post` | Create or schedule a post |
| `social_queue` | List scheduled posts |
| `social_analytics` | Get engagement stats for recent posts |

---

### `social_media_direct` — Direct APIs (4 tools)

| Tool | Description |
|------|-------------|
| `twitter_post` | Post a tweet (Twitter API v2) |
| `linkedin_post` | Publish to LinkedIn (Marketing API) |
| `social_content` | Generate captions with hashtags |
| `social_post_auto` | Auto-route to best available posting method |

---

### `reach` — Content Ingestion (8 tools)

| Tool | Description |
|------|-------------|
| `jina_read` | Read any webpage as clean markdown |
| `web_extract` | Extract content from a URL |
| `youtube_get` | Get transcript + metadata for a YouTube video |
| `youtube_search` | Search YouTube |
| `twitter_read` | Read a tweet or thread |
| `twitter_search` | Search Twitter/X |
| `reddit_read` | Read a Reddit post and comments |
| `reddit_search` | Search Reddit |
| `rss_fetch` | Fetch and parse an RSS/Atom feed |

---

### `second-brain` — Knowledge Vaults (10 tools)

```yaml
toolsets: [second-brain]
```

| Tool | Description |
|------|-------------|
| `second_brain_scaffold` | Create a new domain vault |
| `second_brain_list` | List all vaults |
| `second_brain_raw_list` | List raw/ files (ingested vs pending) |
| `second_brain_read_source` | Read a raw/ source file |
| `second_brain_read_page` | Read a wiki page |
| `second_brain_list_pages` | List wiki pages in a section |
| `second_brain_write_page` | Write/update a wiki page |
| `second_brain_update_index` | Rebuild vault index |
| `second_brain_append_log` | Append to vault activity log |
| `second_brain_lint` | Audit vault health |

---

### `automation` — Cron Jobs (3 tools)

| Tool | Description |
|------|-------------|
| `cron_create` | Schedule a recurring task |
| `cron_list` | List all scheduled tasks |
| `cron_delete` | Delete a scheduled task |

---

### `delegation` — Subagents (4 tools)

| Tool | Description |
|------|-------------|
| `delegate_task` | Spawn subagents for parallel work |
| `delegate_task_async` | Start a delegation in background |
| `check_delegation` | Check if async delegation completed |
| `message_agent` | Send follow-up to a named subagent |

---

### `memory` — Persistent Memory (1 tool)

| Tool | Description |
|------|-------------|
| `memory` | Save durable information across sessions |

---

### `skills` — Skill Management (3 tools)

| Tool | Description |
|------|-------------|
| `skills_list` | List available skills |
| `skill_view` | Load a skill's full content |
| `skill_manage` | Create, update, or delete skills |

---

### `voice` — Phone Calls (7 tools)

Requires: `VAPI_API_KEY` or Fonoster credentials.

| Tool | Description |
|------|-------------|
| `vapi_call` | Make an outbound AI voice call |
| `vapi_calls` | List recent phone calls |
| `fonoster_call_make` | Make an outbound call via Fonoster |
| `fonoster_call_list` | List recent calls |
| `fonoster_number_list` | List registered numbers |
| `fonoster_app_list` | List voice applications |
| `fonoster_agent_create` | Create a SIP agent/extension |

---

### `whatsapp` — Self-Hosted WhatsApp (7 tools)

Requires: `WHATSAPP_API_URL` (WA-JS / evolution-api).

| Tool | Description |
|------|-------------|
| `wa_instance_status` | Check connection status |
| `wa_get_qr` | Get QR/pairing code |
| `wa_get_chats` | List recent conversations |
| `wa_get_messages` | Get messages from a contact |
| `wa_send_text` | Send a text message |
| `wa_send_media` | Send image/video/document/audio |
| `wa_send_button` | Send message with reply buttons |

---

### `homeassistant` — Smart Home (4 tools)

Requires: `HASS_TOKEN`, `HASS_URL`.

| Tool | Description |
|------|-------------|
| `ha_list_entities` | List entities (lights, switches, etc.) |
| `ha_get_state` | Get detailed state of an entity |
| `ha_list_services` | List available services/actions |
| `ha_call_service` | Control a device |

---

### `image_gen` — Image Generation (2 tools)

| Tool | Description |
|------|-------------|
| `image_generate` | Generate images (FLUX 2 Pro via fal.ai) |
| `google_image_generate` | Generate images (Google Gemini) |

---

### Other toolsets

| Toolset | Tools | Requires |
|---------|-------|----------|
| `honcho` | `honcho_context`, `honcho_profile`, `honcho_search`, `honcho_conclude` | `HONCHO_API_KEY` |
| `tts` | `text_to_speech` | `ELEVENLABS_API_KEY` |
| `vision` | `vision_analyze` | LLM with vision |
| `moa` | `mixture_of_agents` | Multiple LLM keys |
| `desktop` | `terminal_run`, `terminal_type`, `claude_code_send` | macOS |
| `rl` | `rl_*` (10 tools) | Local RL environment |
| `avatar` | `heygen_video` | `HEYGEN_API_KEY` |
| `sms-android` | `android_sms_*` (4 tools) | Android SMS Gateway |
| `session_search` | `session_search` | Local sessions |
| `clarify` | `clarify` | Always available |
| `todo` | `todo` | Always available |
| `code_execution` | `execute_code` | Always available |

---

## Adding tools via MCP

Any MCP server can extend Hermes with additional tools:

```yaml
mcp_servers:
  notion:
    url: https://mcp.notion.com/mcp
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_..."
```

MCP tools appear in the agent's tool list automatically.
