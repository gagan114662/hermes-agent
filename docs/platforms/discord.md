# Discord

Connect Hermes to Discord as a bot that responds in servers and DMs.

---

## Prerequisites

- A Discord account
- A Discord application with a bot user

---

## Setup

### 1. Create a Discord application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application**, give it a name
3. Go to **Bot** → **Add Bot**
4. Under **Token**, click **Reset Token** and copy it
5. Enable **Privileged Gateway Intents**:
   - Message Content Intent ✓
   - Server Members Intent ✓ (optional)

### 2. Invite the bot to your server

Under **OAuth2 → URL Generator**:
- Scopes: `bot`, `applications.commands`
- Bot Permissions: `Send Messages`, `Read Message History`, `Embed Links`, `Attach Files`

Copy the generated URL and open it to invite the bot.

### 3. Add credentials

```bash
# ~/.hermes/.env
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5.AbCdEf.xyz...
```

### 4. Start the gateway

```bash
hermes gateway
```

---

## Configuration

### Home channel

Send proactive messages to a specific channel:

```bash
DISCORD_HOME_CHANNEL=1234567890123456789   # channel snowflake ID
DISCORD_HOME_CHANNEL_NAME=general
```

### Require mention

In servers, only respond when the bot is @mentioned:

```bash
DISCORD_REQUIRE_MENTION=true    # default: true in servers
```

### Free-response channels

Channels where the bot responds to every message without needing a mention:

```bash
DISCORD_FREE_RESPONSE_CHANNELS=1234567890,9876543210
```

### Auto-thread

Create a new thread for each conversation:

```bash
DISCORD_AUTO_THREAD=true
```

### Reactions

Enable reaction controls (✅ = done, ❌ = error):

```bash
DISCORD_REACTIONS=true
```

### Allowed users

Restrict who can use the bot (comma-separated user IDs):

```bash
DISCORD_ALLOWED_USERS=123456789,987654321
```

---

## Features

- Text messages in DMs and servers
- @mention detection
- Thread creation
- Voice message transcription (with `OPENAI_API_KEY`)
- Image/file attachments
- Slash commands
- Reaction-based status indicators

---

## Troubleshooting

**Bot is online but doesn't respond**
- Check that **Message Content Intent** is enabled in the developer portal
- In servers, try mentioning the bot: `@MyBot hello`
- Add the channel ID to `DISCORD_FREE_RESPONSE_CHANNELS` for automatic responses

**"Missing Access" errors**
- The bot doesn't have permission to read/send messages in that channel
- Check the bot's role permissions in the server settings

**Bot appears offline**
- Verify `DISCORD_BOT_TOKEN` is correct
- Check gateway logs: `~/.hermes/logs/`
