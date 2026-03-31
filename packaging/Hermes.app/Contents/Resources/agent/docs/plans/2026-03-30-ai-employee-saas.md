# AI Employee SaaS Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a platform that provisions dedicated AI employees (Hermes + OpenWork + Vapi voice + HeyGen face) on per-customer VMs, sold at $299/month with fully automated onboarding and operation.

**Architecture:** A control plane server handles Stripe billing, DigitalOcean VM provisioning, and a Telegram onboarding bot that interviews new customers. Each customer VM runs Hermes + OpenWork with Vapi for voice calls, HeyGen for video avatar, and Twilio for SMS — all auto-configured from the onboarding interview. The AI employee then runs autonomously with cron-driven sales, marketing, and support workflows.

**Tech Stack:** Python, Hermes, OpenWork, Vapi.ai API, HeyGen API, Twilio, Stripe, DigitalOcean API, Cloudflare Pages, Resend.

---

### Task 1: Vapi voice tool for Hermes

**Files:**
- Create: `tools/vapi_tool.py`
- Modify: `model_tools.py` (add `tools.vapi_tool` to `_discover_tools`)
- Modify: `toolsets.py` (add `vapi_call`, `vapi_outbound` to `_HERMES_CORE_TOOLS`)

**What it does:** Lets Hermes make outbound calls and receive inbound call webhooks via Vapi.ai.

**Step 1: Create `tools/vapi_tool.py`**

```python
"""
Vapi Voice Tool — make outbound calls and handle inbound call context via Vapi.ai.

Env vars required:
    VAPI_API_KEY      — Vapi private key
    VAPI_PHONE_ID     — Vapi phone number ID for this agent
    VAPI_ASSISTANT_ID — Vapi assistant ID configured for this agent
"""
import json
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)

VAPI_BASE = "https://api.vapi.ai"


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['VAPI_API_KEY']}",
        "Content-Type": "application/json",
    }


def vapi_outbound_call_tool(phone_number: str, task: str) -> str:
    """Make an outbound call via Vapi to a phone number with a given task/script."""
    payload = {
        "phoneNumberId": os.environ["VAPI_PHONE_ID"],
        "assistantId": os.environ["VAPI_ASSISTANT_ID"],
        "customer": {"number": phone_number},
        "assistantOverrides": {
            "firstMessage": task,
        },
    }
    try:
        resp = httpx.post(
            f"{VAPI_BASE}/call/phone",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return f"Call initiated. Call ID: {data.get('id')}. Status: {data.get('status')}"
    except httpx.HTTPStatusError as e:
        return f"Error making call: {e.response.text}"
    except Exception as e:
        return f"Error: {e}"


def vapi_list_calls_tool(limit: int = 10) -> str:
    """List recent calls handled by this agent."""
    try:
        resp = httpx.get(
            f"{VAPI_BASE}/call",
            headers=_headers(),
            params={"limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        calls = resp.json()
        if not calls:
            return "No calls found."
        lines = ["Recent calls:\n"]
        for c in calls[:limit]:
            cid = c.get("id", "")[:8]
            status = c.get("status", "")
            duration = c.get("duration", 0)
            customer = c.get("customer", {}).get("number", "unknown")
            ended = c.get("endedReason", "")
            lines.append(f"- {cid} | {customer} | {status} | {duration}s | {ended}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def _check_vapi():
    if not os.getenv("VAPI_API_KEY"):
        return False, "VAPI_API_KEY not set"
    if not os.getenv("VAPI_PHONE_ID"):
        return False, "VAPI_PHONE_ID not set"
    return True, "Vapi configured"


registry.register(
    name="vapi_call",
    toolset="voice",
    schema={
        "name": "vapi_call",
        "description": "Make an outbound phone call to a customer using Vapi AI voice. Provide the phone number and what the call should accomplish.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string", "description": "Phone number to call in E.164 format (e.g. +14155552671)"},
                "task": {"type": "string", "description": "What the AI should say/accomplish on this call"},
            },
            "required": ["phone_number", "task"],
        },
    },
    handler=lambda args, **kw: vapi_outbound_call_tool(args["phone_number"], args["task"]),
    check_fn=_check_vapi,
    requires_env=["VAPI_API_KEY", "VAPI_PHONE_ID"],
    emoji="📞",
)

registry.register(
    name="vapi_calls",
    toolset="voice",
    schema={
        "name": "vapi_calls",
        "description": "List recent phone calls handled by this AI agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of calls to return (default 10)", "default": 10},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: vapi_list_calls_tool(args.get("limit", 10)),
    check_fn=_check_vapi,
    requires_env=["VAPI_API_KEY"],
    emoji="📋",
)
```

**Step 2: Add to model_tools.py `_discover_tools()`**

Find:
```python
        "tools.reach_tools",
    ]
```
Replace with:
```python
        "tools.reach_tools",
        "tools.vapi_tool",
    ]
```

**Step 3: Add to `_HERMES_CORE_TOOLS` in toolsets.py**

Find:
```python
    # Reach tools (YouTube, Twitter/X, Reddit, RSS, Jina)
```
Add before it:
```python
    # Voice calls
    "vapi_call", "vapi_calls",
```

**Step 4: Verify import**
```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -c "import tools.vapi_tool; print('vapi_tool OK')"
```
Expected: `vapi_tool OK`

**Step 5: Commit**
```bash
git add tools/vapi_tool.py model_tools.py toolsets.py
git commit -m "feat: add Vapi voice call tool"
```

---

### Task 2: HeyGen avatar tool for Hermes

**Files:**
- Create: `tools/heygen_tool.py`
- Modify: `model_tools.py` (add `tools.heygen_tool`)
- Modify: `toolsets.py` (add `heygen_video` to `_HERMES_CORE_TOOLS`)

**What it does:** Generates a talking-head video of the AI employee's avatar saying a given script.

**Step 1: Create `tools/heygen_tool.py`**

```python
"""
HeyGen Avatar Tool — generate talking-head videos using HeyGen API.

Env vars required:
    HEYGEN_API_KEY   — HeyGen API key
    HEYGEN_AVATAR_ID — Avatar ID for this AI employee
    HEYGEN_VOICE_ID  — Voice ID for this AI employee
"""
import logging
import os
import time
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)

HEYGEN_BASE = "https://api.heygen.com"


def _headers():
    return {
        "X-Api-Key": os.environ["HEYGEN_API_KEY"],
        "Content-Type": "application/json",
    }


def heygen_generate_video_tool(script: str, wait: bool = True) -> str:
    """Generate a talking-head video of the AI employee saying the given script."""
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": os.environ["HEYGEN_AVATAR_ID"],
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": os.environ["HEYGEN_VOICE_ID"],
                },
            }
        ],
        "dimension": {"width": 1280, "height": 720},
    }
    try:
        resp = httpx.post(
            f"{HEYGEN_BASE}/v2/video/generate",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            return f"Error: no video_id in response: {data}"

        if not wait:
            return f"Video generation started. Video ID: {video_id}. Check status with heygen_status tool."

        # Poll for completion (max 3 minutes)
        for _ in range(36):
            time.sleep(5)
            status_resp = httpx.get(
                f"{HEYGEN_BASE}/v1/video_status.get",
                headers=_headers(),
                params={"video_id": video_id},
                timeout=15,
            )
            status_resp.raise_for_status()
            sdata = status_resp.json().get("data", {})
            status = sdata.get("status")
            if status == "completed":
                video_url = sdata.get("video_url", "")
                return f"Video ready: {video_url}"
            elif status == "failed":
                return f"Video generation failed: {sdata.get('error')}"

        return f"Video still processing. Video ID: {video_id}"

    except httpx.HTTPStatusError as e:
        return f"Error: {e.response.text}"
    except Exception as e:
        return f"Error: {e}"


def _check_heygen():
    if not os.getenv("HEYGEN_API_KEY"):
        return False, "HEYGEN_API_KEY not set"
    if not os.getenv("HEYGEN_AVATAR_ID"):
        return False, "HEYGEN_AVATAR_ID not set"
    return True, "HeyGen configured"


registry.register(
    name="heygen_video",
    toolset="avatar",
    schema={
        "name": "heygen_video",
        "description": "Generate a talking-head video of the AI employee avatar saying a given script. Returns a video URL when complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "What the avatar should say in the video"},
                "wait": {"type": "boolean", "description": "Wait for completion and return video URL (default true). Set false to return immediately with video ID.", "default": True},
            },
            "required": ["script"],
        },
    },
    handler=lambda args, **kw: heygen_generate_video_tool(args["script"], args.get("wait", True)),
    check_fn=_check_heygen,
    requires_env=["HEYGEN_API_KEY", "HEYGEN_AVATAR_ID"],
    emoji="🎬",
)
```

**Step 2: Register in model_tools.py and toolsets.py** (same pattern as Task 1)

Add `"tools.heygen_tool"` to `_discover_tools()` and `"heygen_video"` to `_HERMES_CORE_TOOLS`.

**Step 3: Verify**
```bash
venv/bin/python -c "import tools.heygen_tool; print('heygen_tool OK')"
```

**Step 4: Commit**
```bash
git add tools/heygen_tool.py model_tools.py toolsets.py
git commit -m "feat: add HeyGen avatar video tool"
```

---

### Task 3: Twilio SMS tool for Hermes

**Files:**
- Create: `tools/twilio_tool.py`
- Modify: `model_tools.py`, `toolsets.py`

**Step 1: Install twilio SDK**
```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
uv pip install "twilio>=9.0.0,<10" --python venv/bin/python
```
Add `"twilio>=9.0.0,<10"` to `pyproject.toml` dependencies.

**Step 2: Create `tools/twilio_tool.py`**

```python
"""
Twilio SMS Tool — send SMS messages via Twilio.

Env vars:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_PHONE_NUMBER — the agent's Twilio number (e.g. +14155552671)
"""
import logging
import os
from tools.registry import registry

logger = logging.getLogger(__name__)


def sms_send_tool(to: str, message: str) -> str:
    """Send an SMS via Twilio."""
    try:
        from twilio.rest import Client
    except ImportError:
        return "Error: twilio not installed. Run: pip install twilio"

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([sid, token, from_number]):
        return "Error: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER must be set in .env"

    try:
        client = Client(sid, token)
        msg = client.messages.create(body=message, from_=from_number, to=to)
        return f"SMS sent. SID: {msg.sid}. Status: {msg.status}"
    except Exception as e:
        return f"Error sending SMS: {e}"


def _check_twilio():
    if not os.getenv("TWILIO_ACCOUNT_SID"):
        return False, "TWILIO_ACCOUNT_SID not set"
    return True, "Twilio configured"


registry.register(
    name="sms_send",
    toolset="messaging",
    schema={
        "name": "sms_send",
        "description": "Send an SMS message to a phone number via Twilio.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone number in E.164 format (e.g. +14155552671)"},
                "message": {"type": "string", "description": "SMS message body (max 160 chars for single SMS)"},
            },
            "required": ["to", "message"],
        },
    },
    handler=lambda args, **kw: sms_send_tool(args["to"], args["message"]),
    check_fn=_check_twilio,
    requires_env=["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
    emoji="💬",
)
```

**Step 3: Register and verify**
```bash
venv/bin/python -c "import tools.twilio_tool; print('twilio_tool OK')"
```

**Step 4: Commit**
```bash
git add tools/twilio_tool.py model_tools.py toolsets.py pyproject.toml
git commit -m "feat: add Twilio SMS tool"
```

---

### Task 4: VM provisioning script

**Files:**
- Create: `scripts/provision_vm.py`

**What it does:** Given a customer config dict, provisions a DigitalOcean droplet, installs Hermes + OpenWork, writes the customer config, and returns the VM IP + credentials.

**Step 1: Install digitalocean SDK**
```bash
uv pip install "pydo>=0.10.0" --python venv/bin/python
```

**Step 2: Create `scripts/provision_vm.py`**

```python
#!/usr/bin/env python3
"""
Provision a new customer VM on DigitalOcean.

Usage:
    python scripts/provision_vm.py --customer-id <id> --config customer_config.json

Environment:
    DO_API_TOKEN      — DigitalOcean API token
    DO_SSH_KEY_ID     — SSH key ID already added to DigitalOcean account
    DO_REGION         — Region (default: nyc3)
"""
import argparse
import json
import os
import sys
import time
import httpx

DO_BASE = "https://api.digitalocean.com/v2"
HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"
OPENWORK_REPO = "https://github.com/different-ai/openwork.git"


def _do_headers():
    return {
        "Authorization": f"Bearer {os.environ['DO_API_TOKEN']}",
        "Content-Type": "application/json",
    }


# Cloud-init script that installs Hermes + OpenWork + all tools on first boot
CLOUD_INIT_TEMPLATE = """#!/bin/bash
set -e

# Install dependencies
apt-get update -qq
apt-get install -y -qq git curl python3.11 python3.11-venv nodejs npm nginx

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Clone and install Hermes
git clone {hermes_repo} /opt/hermes
cd /opt/hermes
./setup-hermes.sh

# Write .env from customer config
cat > /opt/hermes/.env << 'ENVEOF'
{env_content}
ENVEOF

# Install customer config
mkdir -p /root/.hermes
cat > /root/.hermes/config.yaml << 'CFGEOF'
{hermes_config}
CFGEOF

# Install OpenWork orchestrator
npm install -g openwork-orchestrator

# Install bird for Twitter
npm install -g @steipete/bird

# Start Hermes gateway as systemd service
cat > /etc/systemd/system/hermes-gateway.service << 'SVCEOF'
[Unit]
Description=Hermes Gateway
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/hermes
ExecStart=/root/.local/bin/hermes gateway run
Restart=always
RestartSec=10
EnvironmentFile=/opt/hermes/.env

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable hermes-gateway
systemctl start hermes-gateway

echo "HERMES_READY" > /tmp/hermes_setup_complete
"""


def provision_vm(customer_id: str, customer_config: dict) -> dict:
    """Provision a DigitalOcean VM for a customer. Returns VM details."""
    token = os.environ.get("DO_API_TOKEN")
    if not token:
        raise ValueError("DO_API_TOKEN not set")

    ssh_key_id = os.environ.get("DO_SSH_KEY_ID")
    region = os.environ.get("DO_REGION", "nyc3")

    # Build .env content from customer config
    env_lines = [
        f"HERMES_INFERENCE_PROVIDER=anthropic",
        f"CLAUDE_CODE_OAUTH_TOKEN={customer_config.get('claude_token', '')}",
        f"TELEGRAM_BOT_TOKEN={customer_config.get('telegram_token', '')}",
        f"VAPI_API_KEY={customer_config.get('vapi_api_key', '')}",
        f"VAPI_PHONE_ID={customer_config.get('vapi_phone_id', '')}",
        f"VAPI_ASSISTANT_ID={customer_config.get('vapi_assistant_id', '')}",
        f"HEYGEN_API_KEY={customer_config.get('heygen_api_key', '')}",
        f"HEYGEN_AVATAR_ID={customer_config.get('heygen_avatar_id', '')}",
        f"HEYGEN_VOICE_ID={customer_config.get('heygen_voice_id', '')}",
        f"TWILIO_ACCOUNT_SID={customer_config.get('twilio_sid', '')}",
        f"TWILIO_AUTH_TOKEN={customer_config.get('twilio_token', '')}",
        f"TWILIO_PHONE_NUMBER={customer_config.get('twilio_number', '')}",
        f"CUSTOMER_ID={customer_id}",
        f"BUSINESS_NAME={customer_config.get('business_name', '')}",
    ]

    hermes_config = f"""
agent:
  name: "{customer_config.get('agent_name', 'Alex')}"
  personality: "{customer_config.get('personality', 'professional and helpful')}"
  business_context: |
    Business: {customer_config.get('business_name', '')}
    Industry: {customer_config.get('industry', '')}
    What we sell: {customer_config.get('product', '')}
    Target customer: {customer_config.get('target_customer', '')}
    Tone: {customer_config.get('tone', 'professional')}
"""

    cloud_init = CLOUD_INIT_TEMPLATE.format(
        hermes_repo=HERMES_REPO,
        env_content="\n".join(env_lines),
        hermes_config=hermes_config,
    )

    # Create droplet
    payload = {
        "name": f"hermes-agent-{customer_id}",
        "region": region,
        "size": "s-2vcpu-2gb",  # $12/mo
        "image": "ubuntu-22-04-x64",
        "ssh_keys": [ssh_key_id] if ssh_key_id else [],
        "user_data": cloud_init,
        "tags": ["hermes-agent", f"customer-{customer_id}"],
    }

    resp = httpx.post(f"{DO_BASE}/droplets", headers=_do_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    droplet = resp.json()["droplet"]
    droplet_id = droplet["id"]

    print(f"Droplet created: {droplet_id}. Waiting for IP...")

    # Poll until IP assigned (usually < 60s)
    for _ in range(30):
        time.sleep(5)
        r = httpx.get(f"{DO_BASE}/droplets/{droplet_id}", headers=_do_headers(), timeout=15)
        r.raise_for_status()
        d = r.json()["droplet"]
        networks = d.get("networks", {}).get("v4", [])
        public_ips = [n["ip_address"] for n in networks if n["type"] == "public"]
        if public_ips:
            ip = public_ips[0]
            print(f"VM IP: {ip}")
            return {
                "droplet_id": droplet_id,
                "ip": ip,
                "customer_id": customer_id,
                "status": "provisioning",  # setup-hermes.sh still running
            }

    raise TimeoutError("VM did not get an IP within 150 seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--config", required=True, help="Path to customer config JSON")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    result = provision_vm(args.customer_id, config)
    print(json.dumps(result, indent=2))
```

**Step 3: Test provisioning (dry run)**
```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -c "
import scripts.provision_vm as p
# Just test the cloud-init template renders
cfg = {'business_name': 'Test Co', 'agent_name': 'Alex', 'industry': 'SaaS'}
init = p.CLOUD_INIT_TEMPLATE.format(
    hermes_repo=p.HERMES_REPO,
    env_content='TEST=1',
    hermes_config='agent:\n  name: Alex'
)
print(init[:200])
print('OK')
"
```
Expected: cloud-init script printed, `OK`.

**Step 4: Commit**
```bash
git add scripts/provision_vm.py
git commit -m "feat: add DigitalOcean VM provisioning script"
```

---

### Task 5: Onboarding bot (control plane)

**Files:**
- Create: `scripts/onboarding_bot.py`

**What it does:** A Telegram bot that runs on your control plane server. When a new customer pays (Stripe webhook), it starts a conversation to collect their business info, then calls `provision_vm.py`.

**Step 1: Create `scripts/onboarding_bot.py`**

```python
#!/usr/bin/env python3
"""
Onboarding bot — runs on the control plane.
Interviews new customers over Telegram, provisions their VM.

Env vars:
    ONBOARDING_BOT_TOKEN   — Telegram bot token for onboarding
    DO_API_TOKEN           — DigitalOcean API token
    STRIPE_WEBHOOK_SECRET  — Stripe webhook secret
    HEYGEN_API_KEY         — For creating avatars
    VAPI_API_KEY           — For buying phone numbers
"""
import json
import logging
import os
import uuid
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(BUSINESS_NAME, INDUSTRY, PRODUCT, TARGET_CUSTOMER, TONE,
 AGENT_NAME, HOURS, GOALS, CONFIRM) = range(9)

QUESTIONS = [
    (BUSINESS_NAME, "What's your business name?"),
    (INDUSTRY, "What industry are you in? (e.g. coaching, e-commerce, real estate, consulting)"),
    (PRODUCT, "What do you sell? Describe it in 1-2 sentences."),
    (TARGET_CUSTOMER, "Who is your ideal customer? (e.g. small business owners, homeowners in NYC)"),
    (TONE, "What tone should your AI employee use? (professional / friendly / casual)"),
    (AGENT_NAME, "What would you like to name your AI employee? (e.g. Alex, Jordan, Sam)"),
    (HOURS, "What are your business hours? (e.g. Mon-Fri 9am-5pm EST, or 24/7)"),
    (GOALS, "Main goal: more leads, better customer support, or both?"),
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Welcome! I'm setting up your AI employee.\n\n"
        "I'll ask you 8 quick questions — takes about 2 minutes.\n\n"
        f"{QUESTIONS[0][1]}"
    )
    return BUSINESS_NAME


async def collect_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic handler — stores answer, asks next question."""
    state = update.message.chat.id  # current state tracked by ConversationHandler
    text = update.message.text.strip()

    # Map state to key
    state_keys = {
        BUSINESS_NAME: "business_name",
        INDUSTRY: "industry",
        PRODUCT: "product",
        TARGET_CUSTOMER: "target_customer",
        TONE: "tone",
        AGENT_NAME: "agent_name",
        HOURS: "hours",
        GOALS: "goals",
    }

    # Find current state from context
    current_state = context.user_data.get("_state", BUSINESS_NAME)
    key = state_keys.get(current_state)
    if key:
        context.user_data[key] = text

    # Find next question
    next_state = current_state + 1
    if next_state < len(QUESTIONS):
        context.user_data["_state"] = next_state
        await update.message.reply_text(QUESTIONS[next_state][1])
        return next_state
    else:
        return await confirm(update, context)


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = context.user_data
    summary = (
        f"✅ Here's your AI employee setup:\n\n"
        f"**Business:** {d.get('business_name')}\n"
        f"**Industry:** {d.get('industry')}\n"
        f"**Product:** {d.get('product')}\n"
        f"**Target customer:** {d.get('target_customer')}\n"
        f"**Tone:** {d.get('tone')}\n"
        f"**Agent name:** {d.get('agent_name')}\n"
        f"**Hours:** {d.get('hours')}\n"
        f"**Goal:** {d.get('goals')}\n\n"
        "Type **yes** to confirm and launch your AI employee, or **no** to start over."
    )
    await update.message.reply_text(summary, parse_mode="Markdown")
    return CONFIRM


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text == "yes":
        await update.message.reply_text(
            f"🚀 Launching your AI employee **{context.user_data.get('agent_name')}**...\n\n"
            "This takes about 3-5 minutes. I'll message you when ready!",
            parse_mode="Markdown"
        )
        customer_id = str(uuid.uuid4())[:8]
        await _provision_customer(update, context, customer_id)
        return ConversationHandler.END
    else:
        await update.message.reply_text("No problem! Let's start over.")
        return await start(update, context)


async def _provision_customer(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: str):
    """Provision the VM and report back."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from scripts.provision_vm import provision_vm

    config = dict(context.user_data)
    config["customer_id"] = customer_id

    try:
        result = provision_vm(customer_id, config)
        await update.message.reply_text(
            f"✅ Your AI employee **{config.get('agent_name')}** is live!\n\n"
            f"📞 Phone number: *(being provisioned — will arrive in 5 min)*\n"
            f"💬 Telegram: *(being configured)*\n"
            f"🎬 Video avatar: *(being created)*\n\n"
            f"VM IP: `{result['ip']}`\n"
            f"Customer ID: `{customer_id}`\n\n"
            "You'll get another message in ~5 minutes with your full credentials.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error("Provisioning failed: %s", e)
        await update.message.reply_text(
            f"❌ Provisioning failed: {e}\n\nPlease contact support."
        )


def main():
    token = os.environ["ONBOARDING_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            BUSINESS_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            INDUSTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            TARGET_CUSTOMER: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            TONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            AGENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            GOALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirm)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
```

**Step 2: Verify syntax**
```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -c "import ast; ast.parse(open('scripts/onboarding_bot.py').read()); print('syntax OK')"
```
Expected: `syntax OK`

**Step 3: Commit**
```bash
git add scripts/onboarding_bot.py
git commit -m "feat: add Telegram onboarding bot for customer provisioning"
```

---

### Task 6: Business automation crons

**Files:**
- Create: `skills/business-automation.md`

**What it does:** A Hermes skill that defines the AI employee's daily/weekly automation schedule. Loaded on every customer VM.

**Step 1: Create `skills/business-automation.md`**

```markdown
---
name: business-automation
description: Daily business automation routines for AI employees. Handles prospect research, outreach, follow-ups, and reporting.
version: 1.0.0
---

# Business Automation Skill

You are an AI business employee. Run these automations on schedule:

## Daily (9am business timezone)
1. Research 5 new prospects matching the target customer profile using `reddit_search`, `jina_read`, and `web_search`
2. Send outreach SMS to cold prospects using `sms_send` — keep it brief, value-first
3. Follow up with leads who haven't responded in 3 days via `sms_send`
4. Check for any missed calls via `vapi_calls` and follow up

## Weekly (Monday 8am)
1. Generate a weekly business report: calls made, SMS sent, prospects researched, deals in pipeline
2. Send report to business owner via Telegram using `send_message`
3. Generate a 60-second video update using `heygen_video` and send to owner

## On-demand triggers
- When owner sends "find leads": research 10 new prospects immediately
- When owner sends "call [name] at [number]": make outbound call via `vapi_call`
- When owner sends "send update to customers": draft and send SMS blast
- When owner sends "make video [script]": generate avatar video with `heygen_video`

## Business context
Always load business context from memory before any customer interaction:
- Business name, product, tone
- Known customers and their status
- Active deals and follow-up dates
```

**Step 2: Verify file created**
```bash
ls -la "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent/skills/business-automation.md"
```

**Step 3: Commit**
```bash
git add skills/business-automation.md
git commit -m "feat: add business automation skill for AI employees"
```

---

### Task 7: Landing page

**Files:**
- Create: `website/index.html`

**What it does:** Simple one-page landing with Stripe payment link. Deployable to Cloudflare Pages in one command.

**Step 1: Create `website/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Employee — Your 24/7 AI Business Staff</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #fff; }
  .hero { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 2rem; }
  h1 { font-size: clamp(2rem, 6vw, 4rem); font-weight: 800; line-height: 1.1; margin-bottom: 1.5rem; }
  h1 span { background: linear-gradient(135deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .subtitle { font-size: 1.25rem; color: #888; max-width: 600px; margin-bottom: 3rem; line-height: 1.6; }
  .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; max-width: 800px; margin-bottom: 3rem; }
  .feature { background: #111; border: 1px solid #222; border-radius: 12px; padding: 1.5rem; text-align: left; }
  .feature .icon { font-size: 2rem; margin-bottom: 0.75rem; }
  .feature h3 { font-size: 1rem; font-weight: 600; margin-bottom: 0.5rem; }
  .feature p { font-size: 0.875rem; color: #666; line-height: 1.5; }
  .cta { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; padding: 1rem 3rem; font-size: 1.125rem; font-weight: 700; border-radius: 50px; cursor: pointer; text-decoration: none; display: inline-block; margin-bottom: 1rem; }
  .cta:hover { opacity: 0.9; transform: translateY(-1px); }
  .price { color: #888; font-size: 0.9rem; }
  .price strong { color: #fff; font-size: 1.25rem; }
</style>
</head>
<body>
<section class="hero">
  <h1>Your business,<br>run by <span>AI employees</span></h1>
  <p class="subtitle">An AI employee with a real phone number, a face, and 24/7 availability — handles your sales, marketing, and customer support while you sleep.</p>
  <div class="features">
    <div class="feature">
      <div class="icon">📞</div>
      <h3>Real phone number</h3>
      <p>Answers inbound calls and makes outbound sales calls in your brand voice</p>
    </div>
    <div class="feature">
      <div class="icon">🎬</div>
      <h3>Video face</h3>
      <p>Sends video updates and follow-ups as a lifelike AI avatar</p>
    </div>
    <div class="feature">
      <div class="icon">💬</div>
      <h3>SMS & chat</h3>
      <p>Handles customer support and outreach via text 24/7</p>
    </div>
    <div class="feature">
      <div class="icon">🧠</div>
      <h3>Remembers everything</h3>
      <p>Knows every customer, deal, and interaction — never forgets a follow-up</p>
    </div>
    <div class="feature">
      <div class="icon">📊</div>
      <h3>Weekly reports</h3>
      <p>Sends you a video summary every Monday of what it did for your business</p>
    </div>
    <div class="feature">
      <div class="icon">⚡</div>
      <h3>Live in 5 minutes</h3>
      <p>Answer 8 questions over Telegram — your AI employee is ready instantly</p>
    </div>
  </div>
  <a href="STRIPE_PAYMENT_LINK_HERE" class="cta">Get your AI employee →</a>
  <p class="price"><strong>$299</strong>/month · Cancel anytime · Setup in 5 minutes</p>
</section>
</body>
</html>
```

**Step 2: Replace `STRIPE_PAYMENT_LINK_HERE` with your actual Stripe payment link**

**Step 3: Deploy to Cloudflare Pages**
```bash
npx wrangler pages deploy website/ --project-name ai-employee
```

**Step 4: Commit**
```bash
git add website/
git commit -m "feat: add landing page"
```

---

### Task 8: End-to-end test (manual)

**Step 1: Set test env vars in `.env`**
```bash
# Add to .env for local testing:
VAPI_API_KEY=your_test_key
VAPI_PHONE_ID=your_phone_id
HEYGEN_API_KEY=your_test_key
HEYGEN_AVATAR_ID=your_avatar_id
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx
```

**Step 2: Test all tools load**
```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -c "
import model_tools
from tools.registry import registry
tools = ['vapi_call', 'vapi_calls', 'heygen_video', 'sms_send']
found = [t for t in tools if t in registry._tools]
print('Found:', found)
print('Missing:', [t for t in tools if t not in found])
"
```
Expected: all 4 tools found.

**Step 3: Restart gateway and verify on Telegram**
```bash
~/.local/bin/hermes gateway restart
sleep 5
tail -10 ~/.hermes/logs/gateway.log
```
Expected: `✓ telegram connected`

**Step 4: Send test on Telegram**
Message your bot: "list your available tools"

Expected: bot responds listing vapi_call, heygen_video, sms_send, youtube_get, reddit_search, etc.

**Step 5: Final commit**
```bash
git add .
git commit -m "feat: complete AI employee SaaS foundation"
```
