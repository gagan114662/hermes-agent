# WhatsApp

Hermes supports WhatsApp through a self-hosted WhatsApp Web bridge (WA-JS / evolution-api). This requires running a separate container that holds a WhatsApp Web session.

---

## Prerequisites

- Docker (to run the WhatsApp bridge)
- A WhatsApp account (personal or business)
- A phone with WhatsApp installed

---

## Setup

### 1. Run the WhatsApp bridge

```bash
docker run -d \
  --name wa-bridge \
  -p 3000:3000 \
  -v wa-data:/app/tokens \
  atendai/evolution-api:latest
```

Or with docker-compose:

```yaml
services:
  wa-bridge:
    image: atendai/evolution-api:latest
    ports:
      - "3000:3000"
    volumes:
      - wa-data:/app/tokens
    environment:
      AUTHENTICATION_API_KEY: my_api_key

volumes:
  wa-data:
```

### 2. Connect your phone

```bash
# From Hermes CLI or gateway, call:
wa_get_qr()
```

Or check `http://localhost:3000` and follow the QR code pairing flow.

Scan the QR code with your phone: **WhatsApp → Settings → Linked Devices → Link a Device**.

### 3. Add credentials

```bash
# ~/.hermes/.env
WHATSAPP_ENABLED=true
WHATSAPP_API_URL=http://localhost:3000
WHATSAPP_API_KEY=my_api_key         # if authentication is enabled
WHATSAPP_INSTANCE_ID=default        # instance name configured in the bridge
```

### 4. Start the gateway

```bash
hermes gateway
```

---

## Configuration

### Webhook

The gateway registers a webhook with the bridge automatically. To set the webhook URL manually:

```bash
WHATSAPP_WEBHOOK_URL=https://myserver.com/whatsapp
```

---

## Features

- Text messages
- Images, videos, documents, audio
- Reply buttons (up to 3)
- Group chats
- Voice message transcription
- Contact cards
- Location messages (read-only)

---

## Troubleshooting

**QR code doesn't appear**
- Check the bridge container is running: `docker ps`
- Check bridge logs: `docker logs wa-bridge`

**"Instance not connected"**
- Re-scan the QR code (sessions can expire after ~14 days of inactivity)
- Call `wa_instance_status()` to check connection state

**Messages not arriving in Hermes**
- Verify the webhook is registered with the bridge
- Check `WHATSAPP_API_URL` points to the correct host/port

**Bridge disconnects frequently**
- Keep your phone connected to the internet and not in airplane mode
- Some devices disconnect if WhatsApp is force-stopped; disable battery optimization for WhatsApp
