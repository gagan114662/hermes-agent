# Telegram

Connect Hermes to Telegram so users can message your bot directly.

---

## Prerequisites

- A Telegram account
- A bot token from [@BotFather](https://t.me/botfather)

---

## Setup

### 1. Create a bot

1. Open Telegram and start a chat with [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the prompts
3. Copy the token (format: `123456789:AAF...`)

### 2. Add credentials

```bash
# ~/.hermes/.env
TELEGRAM_BOT_TOKEN=123456789:AAFabcdefghijklmnopqrstuvwxyz
```

### 3. Start the gateway

```bash
hermes gateway
```

The bot is now live. Send it a message on Telegram.

---

## Configuration

### Home channel

Set a default channel where Hermes sends proactive messages (reminders, alerts):

```bash
TELEGRAM_HOME_CHANNEL=@my_channel       # or numeric chat ID: -1001234567890
TELEGRAM_HOME_CHANNEL_NAME=Home
```

### Reply mode

```bash
TELEGRAM_REPLY_TO_MODE=thread    # reply in-thread (default)
TELEGRAM_REPLY_TO_MODE=message   # reply as new message
```

### Require mention

In groups, only respond when the bot is mentioned:

```bash
TELEGRAM_REQUIRE_MENTION=true
```

Or per-chat free-response channels (comma-separated chat IDs where the bot responds to everything):

```bash
TELEGRAM_FREE_RESPONSE_CHATS=-1001234567890,-1009876543210
```

### Custom mention patterns

```bash
# JSON array of regex patterns that count as a mention
TELEGRAM_MENTION_PATTERNS='["hermes", "assistant", "@mybot"]'
```

---

## Webhook Mode

By default Hermes uses long-polling. For production, use webhooks:

```bash
TELEGRAM_WEBHOOK_URL=https://myserver.com/telegram
TELEGRAM_WEBHOOK_PORT=8443
TELEGRAM_WEBHOOK_SECRET=my_secret_token   # optional but recommended
```

Telegram requires HTTPS with a valid certificate on port 443, 80, 88, or 8443.

---

## Fallback IPs

If Telegram is blocked in your region, configure fallback IP addresses:

```bash
TELEGRAM_FALLBACK_IPS=149.154.167.220,149.154.175.100
```

---

## Features

- Text messages
- Voice messages (auto-transcribed with Whisper if `OPENAI_API_KEY` is set)
- Images (passed to vision tools)
- Documents (PDF, text files, etc.)
- Group chats
- Inline commands (`/start`, `/help`, etc.)
- Markdown rendering (MarkdownV2)
- Long response splitting (messages > 4096 chars are split automatically)

---

## Troubleshooting

**Bot doesn't respond**
- Check `TELEGRAM_BOT_TOKEN` is correct
- Ensure the gateway is running (`hermes gateway`)
- Check logs: `tail -f ~/.hermes/logs/*.log`

**"Unauthorized" error**
- The token is invalid or the bot was deleted. Re-create with BotFather.

**Bot only works in private chats, not groups**
- Add `TELEGRAM_REQUIRE_MENTION=false` or add the chat ID to `TELEGRAM_FREE_RESPONSE_CHATS`
- Make sure the bot has been added to the group and granted message permissions
