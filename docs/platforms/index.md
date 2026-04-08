# Platform Guides

Hermes connects to 15+ messaging platforms through the gateway. Each platform requires its own credentials; platforms are auto-detected from the environment.

---

## Supported Platforms

| Platform | Guide | Required env vars |
|----------|-------|-------------------|
| Telegram | [Setup →](telegram.md) | `TELEGRAM_BOT_TOKEN` |
| Discord | [Setup →](discord.md) | `DISCORD_BOT_TOKEN` |
| Slack | [Setup →](slack.md) | `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` |
| WhatsApp (self-hosted) | [Setup →](whatsapp.md) | `WHATSAPP_ENABLED=true` + API URL |
| Signal | [Setup →](signal.md) | `SIGNAL_HTTP_URL` + `SIGNAL_ACCOUNT` |
| Email (IMAP/SMTP) | [Setup →](email.md) | `EMAIL_ADDRESS` + `EMAIL_PASSWORD` + hosts |
| Matrix | [Setup →](matrix.md) | `MATRIX_ACCESS_TOKEN` + `MATRIX_HOMESERVER` |
| SMS (Twilio) | [Setup →](sms.md) | `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` |
| DingTalk / Feishu / WeCom | [Setup →](enterprise-cn.md) | Platform-specific |
| Mattermost | [Setup →](mattermost.md) | `MATTERMOST_TOKEN` + `MATTERMOST_URL` |
| Home Assistant | [Setup →](homeassistant.md) | `HASS_TOKEN` |

---

## Starting the Gateway

```bash
hermes gateway
```

The gateway auto-detects which platforms are configured and starts adapters for each. It prints a summary at startup:

```
✓ Telegram — connected (@my_bot)
✓ Discord — connected
✗ Slack — SLACK_BOT_TOKEN not set
```

---

## Multiple Platforms Simultaneously

All configured platforms run in the same gateway process. A single Hermes instance handles messages from all of them, maintaining separate sessions per platform+user.

---

## Session Isolation

Each `(platform, user_id)` pair gets its own session:
- Separate memory context
- Separate conversation history
- Shared skills and tool access

---

## Rate Limiting

By default each user is limited to 20 messages/minute with a burst of 5. Configurable via:

```bash
GATEWAY_RATE_LIMIT_PER_MINUTE=30
GATEWAY_RATE_LIMIT_BURST=10
GATEWAY_RATE_LIMIT_ENABLED=false  # disable
```
