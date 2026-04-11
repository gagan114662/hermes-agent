# Signal

Connect Hermes to Signal via the [signal-cli](https://github.com/AsamK/signal-cli) HTTP API.

---

## Prerequisites

- signal-cli installed and a Signal account registered
- signal-cli running in HTTP daemon mode

---

## Setup

### 1. Register a Signal account with signal-cli

```bash
# Install signal-cli (macOS)
brew install signal-cli

# Register with a phone number
signal-cli -a +1XXXXXXXXXX register

# Verify with the SMS code you receive
signal-cli -a +1XXXXXXXXXX verify 123456
```

### 2. Start signal-cli in HTTP mode

```bash
signal-cli -a +1XXXXXXXXXX daemon --http 127.0.0.1:8080
```

Or as a systemd service:

```ini
[Unit]
Description=signal-cli HTTP daemon

[Service]
ExecStart=signal-cli -a +1XXXXXXXXXX daemon --http 127.0.0.1:8080
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3. Add credentials

```bash
# ~/.hermes/.env
SIGNAL_HTTP_URL=http://127.0.0.1:8080
SIGNAL_ACCOUNT=+1XXXXXXXXXX
```

### 4. Start the gateway

```bash
hermes gateway
```

---

## Configuration

### Home channel

```bash
SIGNAL_HOME_CHANNEL=+1XXXXXXXXXX   # phone number or group ID
SIGNAL_HOME_CHANNEL_NAME=Home
```

### Ignore Stories

Stories are ignored by default. To include them:

```bash
SIGNAL_IGNORE_STORIES=false
```

### Group access control

Restrict which group members can interact with the bot:

```bash
# Comma-separated phone numbers
SIGNAL_GROUP_ALLOWED_USERS=+1XXXXXXXXXX,+44XXXXXXXXXX
```

---

## Features

- Text messages
- Group messages
- Image/file attachments
- Voice messages (transcribed with Whisper)
- End-to-end encrypted (Signal protocol)
- Read receipts

---

## Troubleshooting

**"SIGNAL_HTTP_URL and SIGNAL_ACCOUNT must both be set"**
- Both env vars are required. Check your `.env` file.

**signal-cli connection refused**
- Ensure the daemon is running: `curl http://127.0.0.1:8080/v1/about`
- Check signal-cli version: some API endpoints require signal-cli 0.11+

**"Device is not registered"**
- Re-register the account with signal-cli. The device may have been unlinked.

**Messages arrive but responses don't send**
- Check signal-cli logs for send errors
- Verify the account has not been rate-limited by Signal
