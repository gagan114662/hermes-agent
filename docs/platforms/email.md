# Email (IMAP/SMTP)

Connect Hermes to any email account via IMAP (receive) and SMTP (send).

---

## Prerequisites

- An email account with IMAP/SMTP access
- IMAP and SMTP host names and ports for your provider

---

## Setup

### 1. Enable IMAP in your email provider

=== "Gmail"
    1. Go to **Settings → See all settings → Forwarding and POP/IMAP**
    2. Enable **IMAP**
    3. If using 2FA, create an **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
    4. Use the app password as `EMAIL_PASSWORD`

=== "Outlook / Hotmail"
    1. IMAP is enabled by default
    2. Use your Microsoft account password (or app password if MFA is on)

=== "Custom / Self-hosted"
    Use your server's IMAP and SMTP settings directly.

### 2. Add credentials

```bash
# ~/.hermes/.env
EMAIL_ADDRESS=mybot@gmail.com
EMAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx    # app password if using 2FA

EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993

EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
```

### 3. Optional: home address

Set a default recipient for proactive outbound emails:

```bash
EMAIL_HOME_ADDRESS=owner@example.com
EMAIL_HOME_ADDRESS_NAME=Owner
```

### 4. Start the gateway

```bash
hermes gateway
```

Hermes polls the inbox for new messages and replies via SMTP.

---

## Common Provider Settings

| Provider | IMAP host | IMAP port | SMTP host | SMTP port |
|----------|-----------|-----------|-----------|-----------|
| Gmail | `imap.gmail.com` | 993 | `smtp.gmail.com` | 587 |
| Outlook | `outlook.office365.com` | 993 | `smtp.office365.com` | 587 |
| Yahoo | `imap.mail.yahoo.com` | 993 | `smtp.mail.yahoo.com` | 587 |
| iCloud | `imap.mail.me.com` | 993 | `smtp.mail.me.com` | 587 |
| Fastmail | `imap.fastmail.com` | 993 | `smtp.fastmail.com` | 587 |
| ProtonMail | `127.0.0.1` | 1143 | `127.0.0.1` | 1025 | (via ProtonMail Bridge) |

---

## Features

- Receive emails and reply in-thread
- Send new emails via `gmail_send` tool (Google Workspace) or `send_message` tool
- HTML and plain-text rendering
- Attachment handling (read PDF, text, images)
- Voice note transcription (audio attachments)

---

## Troubleshooting

**"IMAP authentication failed"**
- Gmail: use an App Password, not your regular password
- Check IMAP is enabled in the provider settings
- Try connecting with a regular IMAP client (Thunderbird) first to verify credentials

**"SMTP connection refused"**
- Check port and host are correct for your provider
- Port 587 requires STARTTLS; port 465 requires SSL. Most providers use 587.

**Hermes not picking up new emails**
- Check polling interval (default: 30s)
- Verify the inbox is not filtered by provider into Spam

**Replies going to spam**
- Configure SPF/DKIM for your domain
- Use a dedicated transactional email address, not a personal one
