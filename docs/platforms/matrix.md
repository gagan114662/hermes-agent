# Matrix

Connect Hermes to any Matrix homeserver (matrix.org, Element, Synapse, Dendrite, etc.).

---

## Prerequisites

- A Matrix account on any homeserver
- The homeserver URL
- An access token or password

---

## Setup

### Option A: Access Token (recommended)

1. Log in to your Matrix account (e.g., via Element)
2. Go to **Settings → Help & About → Advanced → Access Token**
3. Copy the token

```bash
# ~/.hermes/.env
MATRIX_ACCESS_TOKEN=syt_abc123...
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER_ID=@mybot:matrix.org
```

### Option B: Password login

```bash
# ~/.hermes/.env
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER_ID=@mybot:matrix.org
MATRIX_PASSWORD=my_password
```

### Home room

```bash
MATRIX_HOME_ROOM=!roomid:matrix.org
MATRIX_HOME_ROOM_NAME=Home
```

### 4. Start the gateway

```bash
hermes gateway
```

---

## End-to-End Encryption

Enable E2EE (requires `libolm`):

```bash
MATRIX_ENCRYPTION=true
pip install matrix-nio[e2e]
```

!!! note
    E2EE requires a persistent device store. The store is kept in `~/.hermes/matrix/`.

---

## Features

- Direct messages
- Room messages
- End-to-end encryption (optional)
- File attachments
- Voice message transcription
- Federated — works across any homeserver

---

## Troubleshooting

**"M_FORBIDDEN" or login errors**
- Verify `MATRIX_HOMESERVER` URL (include `https://`)
- Check `MATRIX_USER_ID` format: `@username:homeserver.tld`
- If using a token, generate a fresh one (tokens expire after logout)

**Bot joins room but doesn't respond**
- The bot must be invited to the room first
- In private rooms, invite the bot: `/invite @mybot:matrix.org`

**E2EE: "Unable to decrypt message"**
- Ensure `libolm` is installed: `pip install libolm`
- The bot needs to be in the room before messages are sent (keys aren't retroactive)
