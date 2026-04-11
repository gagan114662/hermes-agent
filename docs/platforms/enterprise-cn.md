# DingTalk / Feishu / WeCom

Three enterprise messaging platforms common in Chinese organizations.

---

## DingTalk

### Prerequisites

- A DingTalk developer account
- A DingTalk application (企业内部应用 or 第三方应用)

### Setup

1. Go to [open.dingtalk.com](https://open.dingtalk.com)
2. Create a new application
3. Under **Application Credentials**, copy **Client ID** and **Client Secret**
4. Configure the event webhook endpoint (事件订阅)

```bash
# ~/.hermes/.env
DINGTALK_CLIENT_ID=ding_xxxxxxxxxxxx
DINGTALK_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxx
```

Start the gateway:

```bash
hermes gateway
```

---

## Feishu (Lark)

### Prerequisites

- A Feishu/Lark workspace
- An app created in the [Feishu Developer Console](https://open.feishu.cn)

### Setup

1. Create an app in the Feishu Open Platform
2. Under **Credentials & Basic Info**, copy **App ID** and **App Secret**
3. Configure **Event Subscriptions** with your webhook URL
4. Add bot capabilities

```bash
# ~/.hermes/.env
FEISHU_APP_ID=cli_xxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx

# Optional: message encryption
FEISHU_ENCRYPT_KEY=your_encrypt_key
FEISHU_VERIFICATION_TOKEN=your_verification_token

# Optional: restrict to specific users
FEISHU_ALLOWED_USERS=ou_xxxx,ou_yyyy

# Connection mode: "websocket" (default) or "webhook"
FEISHU_CONNECTION_MODE=websocket

# Webhook settings (if using webhook mode)
FEISHU_WEBHOOK_HOST=0.0.0.0
FEISHU_WEBHOOK_PORT=8080

# Domain: "feishu" (China) or "lark" (international)
FEISHU_DOMAIN=feishu
```

Start the gateway:

```bash
hermes gateway
```

### Feishu Features

- Text messages
- Rich text / cards
- File attachments
- Group chats
- @mentions
- Reaction emojis
- WebSocket mode (no public URL needed) or HTTP webhook mode

---

## WeCom (企业微信 / WeChat Work)

### Prerequisites

- A WeCom enterprise account
- A custom application created in the WeCom admin console

### Setup

1. Log in to [work.weixin.qq.com/wework_admin](https://work.weixin.qq.com/wework_admin)
2. Go to **Applications → Create Application**
3. Copy the **CorpID** and application **Secret**
4. Configure a Receiving Message API with your webhook URL

```bash
# ~/.hermes/.env
WECOM_CORP_ID=ww_xxxxxxxxxx
WECOM_SECRET=xxxxxxxxxxxxxxxxxxxx
WECOM_AGENT_ID=1000001

# Optional: WebSocket URL (if using enterprise internal proxy)
WECOM_WEBSOCKET_URL=wss://...
```

Start the gateway:

```bash
hermes gateway
```

### WeCom Features

- Text messages
- Markdown messages
- Image/file attachments
- Group chats
- WeCom bots (企业微信机器人)
- Message card templates

---

## Troubleshooting

**DingTalk: "Invalid client credentials"**
- Verify `DINGTALK_CLIENT_ID` and `DINGTALK_CLIENT_SECRET` are from the same app
- Check the app is published/activated in the DingTalk developer portal

**Feishu: Webhook not receiving events**
- Add your server IP to the allowlist in the Feishu app settings
- Check `FEISHU_VERIFICATION_TOKEN` matches the one in the developer console
- In WebSocket mode, no public URL is required — just start the gateway

**WeCom: "40014: invalid access_token"**
- Access tokens expire every 2 hours; Hermes refreshes automatically
- Check `WECOM_CORP_ID` and `WECOM_SECRET` are correct
