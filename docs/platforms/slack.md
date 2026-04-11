# Slack

Connect Hermes to Slack using Socket Mode (no public webhook URL needed).

---

## Prerequisites

- A Slack workspace where you have admin access
- A Slack app with Socket Mode enabled

---

## Setup

### 1. Create a Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App → From scratch**
3. Give it a name and choose your workspace

### 2. Configure OAuth scopes

Under **OAuth & Permissions → Scopes → Bot Token Scopes**, add:

```
app_mentions:read
channels:history
channels:read
chat:write
files:read
groups:history
groups:read
im:history
im:read
im:write
mpim:history
mpim:read
mpim:write
users:read
```

### 3. Enable Socket Mode

Under **Socket Mode**, toggle **Enable Socket Mode** on.

Generate an **App-Level Token** with scope `connections:write`. Copy it (starts with `xapp-`).

### 4. Enable Event Subscriptions

Under **Event Subscriptions**, toggle on. Subscribe to these bot events:

```
message.channels
message.groups
message.im
message.mpim
app_mention
```

### 5. Install to workspace

Under **OAuth & Permissions**, click **Install to Workspace** and authorize.

Copy the **Bot User OAuth Token** (starts with `xoxb-`).

### 6. Add credentials

```bash
# ~/.hermes/.env
SLACK_BOT_TOKEN=xoxb-1234567890-...
SLACK_APP_TOKEN=xapp-1-...
```

### 7. Start the gateway

```bash
hermes gateway
```

---

## Configuration

### Home channel

```bash
SLACK_HOME_CHANNEL=C1234567890    # channel ID
SLACK_HOME_CHANNEL_NAME=general
```

To find a channel ID: right-click the channel in Slack → **Copy link** → the ID is the last segment.

---

## Features

- Direct messages
- Channel messages (when mentioned)
- File uploads / attachments
- Voice message transcription
- Thread replies
- Block Kit rich message formatting

---

## Troubleshooting

**Bot doesn't appear in workspace**
- Make sure you clicked **Install to Workspace** after adding scopes

**"not_authed" or "invalid_auth" errors**
- Check `SLACK_BOT_TOKEN` starts with `xoxb-`
- Check `SLACK_APP_TOKEN` starts with `xapp-`

**Bot doesn't respond in channels**
- Invite the bot to the channel: `/invite @MyBot`
- Or mention the bot: `@MyBot hello`

**Socket Mode connection fails**
- Verify the App-Level Token has `connections:write` scope
- Socket Mode must be enabled in the app settings
