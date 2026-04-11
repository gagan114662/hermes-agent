# Messaging Tools

Tools for sending messages across connected platforms.

## `send_message`

Send a message to any connected platform:

```
send_message(platform="telegram", chat_id="@username", text="Hello!")
send_message(platform="discord", channel_id="1234567890", text="Hello!")
```

Without arguments, lists available targets.

## `sms_send`

Send SMS via Twilio. Requires `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`.

```
sms_send(to="+1XXXXXXXXXX", message="Hello from Hermes!")
```

## `whatsapp_send`

Send WhatsApp via Twilio WhatsApp Business API. Requires the same Twilio credentials plus a WhatsApp-enabled number.

```
whatsapp_send(to="+1XXXXXXXXXX", message="Hello from Hermes!")
```

For self-hosted WhatsApp (WA-JS/evolution-api), use the `whatsapp` toolset instead — see [WhatsApp platform guide](../platforms/whatsapp.md).
