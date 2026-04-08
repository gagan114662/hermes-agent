# Mattermost

Connect Hermes to a self-hosted or cloud Mattermost instance.

---

## Prerequisites

- A Mattermost server (self-hosted or Mattermost Cloud)
- A bot account with an access token

---

## Setup

### 1. Create a bot account

1. Go to **System Console → Integrations → Bot Accounts**
2. Click **Add Bot Account**
3. Give the bot a username, display name, and role
4. Copy the **Access Token** (shown only once — save it)

Alternatively, create a personal access token for an existing user:
**Account Settings → Security → Personal Access Tokens → Create Token**

### 2. Add the bot to channels

Invite the bot to any channels where it should respond:
```
/invite @mybot
```

### 3. Add credentials

```bash
# ~/.hermes/.env
MATTERMOST_TOKEN=xxxxxxxxxxxxxxxxxxxx
MATTERMOST_URL=https://mattermost.example.com
```

### 4. Home channel

```bash
MATTERMOST_HOME_CHANNEL=channelid123   # channel ID (not name)
MATTERMOST_HOME_CHANNEL_NAME=Town Square
```

To find a channel ID: in Mattermost, go to the channel → **View Info** → Channel ID.

### 5. Start the gateway

```bash
hermes gateway
```

---

## Features

- Direct messages
- Channel messages (when mentioned)
- File attachments
- Voice message transcription
- Markdown formatting
- Slash commands
- Message reactions
- WebSocket real-time connection

---

## Troubleshooting

**"401 Unauthorized"**
- Verify the token is correct and not expired
- Bot accounts don't expire; personal access tokens may

**Bot doesn't receive channel messages**
- Ensure the bot is a member of the channel
- Check the bot has the `create_post` permission

**"MATTERMOST_URL must be set"**
- Both `MATTERMOST_TOKEN` and `MATTERMOST_URL` are required
- Include the protocol: `https://mattermost.example.com` (no trailing slash)

**WebSocket disconnects frequently**
- Check your Mattermost server's WebSocket idle timeout settings
- The gateway reconnects automatically on disconnect
