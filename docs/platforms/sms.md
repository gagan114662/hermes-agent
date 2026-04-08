# SMS (Twilio)

Connect Hermes to SMS via Twilio — send and receive text messages from any phone number.

---

## Prerequisites

- A [Twilio](https://twilio.com) account
- A Twilio phone number with SMS capabilities

---

## Setup

### 1. Get Twilio credentials

1. Log in to the [Twilio Console](https://console.twilio.com)
2. From the dashboard, copy:
   - **Account SID** (starts with `AC`)
   - **Auth Token**
3. Under **Phone Numbers → Manage → Active Numbers**, find or buy a number

### 2. Add credentials

```bash
# ~/.hermes/.env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
```

### 3. Configure the webhook

In the Twilio Console, for your phone number under **Messaging**:
- Set **A message comes in** → **Webhook** → `https://yourserver.com/sms`
- Method: `POST`

The gateway starts an HTTP server for incoming webhooks. The default port is `8443`. Configure the public URL:

```bash
SMS_WEBHOOK_PORT=8443
```

Or use ngrok for local testing:

```bash
ngrok http 8443
# Set the ngrok URL in Twilio Console
```

### 4. Home channel

Set a phone number for proactive outbound SMS:

```bash
SMS_HOME_CHANNEL=+1XXXXXXXXXX
SMS_HOME_CHANNEL_NAME=Owner
```

### 5. Start the gateway

```bash
hermes gateway
```

---

## Features

- Inbound SMS → Hermes responds
- Outbound SMS via `sms_send` tool
- MMS (images, media)
- Alphanumeric sender ID (where supported)

---

## Troubleshooting

**"Unable to create record" from Twilio**
- The destination number must be verified in trial accounts
- Upgrade from trial or add the number under **Verified Caller IDs**

**Webhook not receiving messages**
- Check the webhook URL in Twilio Console is correct and reachable
- Use `ngrok` for local development and update the webhook URL

**"AuthenticationError: Authentication Error"**
- Verify `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` match the values in your Twilio Console

**High latency on responses**
- Twilio has a 15s timeout for webhook responses. Long agent runs will cause Twilio to retry.
- Consider acknowledging the webhook immediately and sending the response asynchronously
