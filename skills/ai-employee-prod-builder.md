---
name: ai-employee-prod-builder
description: Master builder skill for finishing the AI Employee SaaS product to production-grade. Executes sprint by sprint to fix critical bugs, harden the codebase, and deploy. Run one sprint at a time.
version: 1.0.0
---

# AI Employee Production Builder

You are the builder. Your job is to make the AI Employee SaaS production-ready and monetizable. Work through the sprints in order. Use your terminal_tool and file editing capabilities to implement each task. After each task, show the diff and confirm it's done.

**Repo location:** `~/Desktop/my\ projects/hermes/hermes-agent`
**All file paths below are relative to the repo root.**

---

## Sprint 1 — P0 Critical Fixes

*Nothing works for customers without these. Run this first.*

### Task 1 — Update PayPal merchant email

Ask: "What is your PayPal email address for receiving $299/month payments?"

Then in `website/index.html`, replace `vandan@getfoolish.com` with the email provided.

Verify: `grep -n "paypal\|vandan\|getfoolish" website/index.html`

---

### Task 2 — Fix systemd EnvironmentFile bug

In `scripts/provision_vm.py`, find the cloud-init template string. Inside the `[Service]` block of the systemd unit, find the line with a leading space before `EnvironmentFile`:

```
 EnvironmentFile=/opt/hermes/.env
```

Remove the leading space so it reads:

```
EnvironmentFile=/opt/hermes/.env
```

Verify: `grep -n "EnvironmentFile" scripts/provision_vm.py`

---

### Task 3 — Inject missing env vars into customer VMs

In `scripts/provision_vm.py`, find the section where `env_vars` dict is built (the block with `CLAUDE_CODE_OAUTH_TOKEN`, `TELEGRAM_BOT_TOKEN`, etc.).

Add these three lines to the same dict:

```python
"CONTROL_PLANE_URL": os.environ.get("CONTROL_PLANE_URL", ""),
"VAPI_WEBHOOK_SECRET": os.environ.get("VAPI_WEBHOOK_SECRET", ""),
"PAYPAL_WEBHOOK_ID": os.environ.get("PAYPAL_WEBHOOK_ID", ""),
```

Verify: `grep -n "CONTROL_PLANE_URL\|VAPI_WEBHOOK_SECRET\|PAYPAL_WEBHOOK_ID" scripts/provision_vm.py`

---

### Task 4 — Auto-provision Vapi phone number

In `scripts/provision_vm.py`, add a new function after the imports section:

```python
def buy_vapi_phone(vapi_api_key: str, area_code: str = "415") -> dict:
    """Purchase a Vapi phone number for a new customer. Returns {id, number}."""
    import urllib.request, json as _json
    payload = _json.dumps({"provider": "twilio", "areaCode": area_code}).encode()
    req = urllib.request.Request(
        "https://api.vapi.ai/phone-number",
        data=payload,
        headers={
            "Authorization": f"Bearer {vapi_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = _json.loads(resp.read())
    return {"id": data.get("id", ""), "number": data.get("number", "")}
```

Then, after the droplet IP is obtained and before returning, call it:

```python
vapi_key = customer_config.get("VAPI_API_KEY") or os.environ.get("VAPI_API_KEY", "")
vapi_phone = {}
if vapi_key:
    try:
        vapi_phone = buy_vapi_phone(vapi_key)
        env_vars["VAPI_PHONE_ID"] = vapi_phone.get("id", "")
        env_vars["VAPI_PHONE_NUMBER"] = vapi_phone.get("number", "")
        logger.info(f"Vapi phone provisioned: {vapi_phone.get('number')}")
    except Exception as e:
        logger.warning(f"Vapi phone provisioning failed (non-fatal): {e}")
```

Add `vapi_phone_number` to the return dict:

```python
return {
    "droplet_id": droplet_id,
    "ip": ip,
    "customer_id": customer_id,
    "status": "provisioned",
    "vapi_phone_number": vapi_phone.get("number", ""),
}
```

Verify: `grep -n "buy_vapi_phone\|vapi_phone" scripts/provision_vm.py`

---

### Task 5 — Fix webhook secret

Read `~/.hermes/config.yaml`. Find the line with `INSECURE_NO_AUTH`. Generate a secure replacement:

```python
import secrets
secret = secrets.token_hex(32)
print(secret)
```

Replace `INSECURE_NO_AUTH` in `~/.hermes/config.yaml` with the generated secret.
Write the secret to `~/.hermes/.webhook_secret` for reference.

Tell the user: "Your new Vapi webhook secret is: {secret} — add this to your Vapi dashboard under Server URL secret."

---

### Sprint 1 Complete

Run: `cd ~/Desktop/my\ projects/hermes/hermes-agent && git diff --stat`

Report all 5 tasks as ✅ or ❌ with reason.

---

## Sprint 2 — Onboarding Hardening

*Wraps provisioning in error handling so customers get notified on failure.*

### Task 1 — Error handling for provision_vm

In `scripts/onboarding_bot.py`, find the line `result = provision_vm(customer_id, dict(context.user_data))`.

Replace the bare call with a try/except block:

```python
await update.message.reply_text("⏳ Setting up your AI employee... this takes about 2 minutes.")
try:
    result = provision_vm(customer_id, dict(context.user_data))
    ip = result.get("ip", "unknown")
    phone = result.get("vapi_phone_number", "being set up")
    await update.message.reply_text(
        f"✅ Your AI employee is live!\n\n"
        f"📞 Phone: {phone}\n"
        f"💬 Telegram: @hermes114bot\n\n"
        f"It will start working within 5 minutes."
    )
    # Notify owner
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if owner_id:
        await context.bot.send_message(
            chat_id=owner_id,
            text=f"🎉 New customer live!\nID: {customer_id}\nIP: {ip}\nPhone: {phone}\nBusiness: {context.user_data.get('business_name', '?')}",
        )
    # Notify control plane
    control_plane_url = os.environ.get("CONTROL_PLANE_URL", "")
    if control_plane_url:
        import urllib.request, json as _json
        payload = _json.dumps({
            "customer_id": customer_id,
            "ip": ip,
            "phone": phone,
            "telegram_chat_id": str(update.effective_chat.id),
        }).encode()
        req = urllib.request.Request(
            f"{control_plane_url}/internal/customer-ready",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # Non-fatal
except Exception as e:
    logger.error(f"Provisioning failed for {customer_id}: {e}")
    await update.message.reply_text(
        "⚠️ Setup hit a snag. Our team has been notified and will fix it within 1 hour. "
        "You will not be charged if we cannot deliver."
    )
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if owner_id:
        await context.bot.send_message(
            chat_id=owner_id,
            text=f"🚨 Provisioning FAILED\nCustomer: {customer_id}\nError: {e}\nData: {dict(context.user_data)}",
        )
```

Verify: `grep -n "try:\|except\|ProvisioningFailed\|⏳" scripts/onboarding_bot.py`

---

### Sprint 2 Complete

Run: `cd ~/Desktop/my\ projects/hermes/hermes-agent && venv/bin/python -m pytest tests/ -q -x 2>&1 | tail -10`

Report result.

---

## Sprint 3 — Control Plane Production Hardening

*Replaces JSON storage with SQLite and adds admin commands.*

### Task 1 — SQLite migration

In `scripts/control_plane.py`, add SQLite support:

1. Add import at top: `import sqlite3`
2. Add DB path constant: `DB_PATH = Path.home() / ".hermes" / "customers.db"`
3. Add `init_db()` function:

```python
def init_db() -> None:
    """Initialize SQLite DB and migrate from JSON if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            telegram_chat_id TEXT,
            paypal_payer_id TEXT,
            email TEXT,
            ip TEXT,
            phone TEXT,
            status TEXT DEFAULT 'onboarding',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    # Migrate from JSON if exists
    json_path = Path.home() / ".hermes" / "customers.json"
    if json_path.exists():
        import json
        data = json.loads(json_path.read_text())
        for cid, c in data.get("customers", {}).items():
            conn.execute(
                "INSERT OR IGNORE INTO customers (customer_id, email, paypal_payer_id, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (cid, c.get("email",""), c.get("payer_id",""), c.get("status","onboarding"), c.get("created_at",""), c.get("created_at","")),
            )
        conn.commit()
        json_path.rename(json_path.with_suffix(".json.bak"))
        logger.info("Migrated customers.json → customers.db")
    conn.close()
```

4. Call `init_db()` at startup (in the `lifespan` or at module level).

5. Replace any remaining `customers.json` reads/writes with SQLite queries using the pattern:
```python
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
# ... query ...
conn.close()
```

---

### Task 2 — Add /internal/customer-ready endpoint

```python
@app.post("/internal/customer-ready")
async def customer_ready(request: Request) -> dict:
    body = await request.json()
    customer_id = body.get("customer_id", "")
    ip = body.get("ip", "")
    phone = body.get("phone", "")
    telegram_chat_id = body.get("telegram_chat_id", "")
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE customers SET ip=?, phone=?, telegram_chat_id=?, status='active', updated_at=? WHERE customer_id=?",
        (ip, phone, telegram_chat_id, now, customer_id),
    )
    conn.commit()
    conn.close()
    # Notify customer via Telegram
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if bot_token and telegram_chat_id:
        msg = f"🎉 Your AI employee is ready!\n\n📞 Phone: {phone}\n\nStart sending it tasks via @hermes114bot"
        import urllib.request
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={telegram_chat_id}&text={urllib.parse.quote(msg)}",
            timeout=10,
        )
    return {"ok": True}
```

---

### Task 3 — Admin endpoint

```python
@app.post("/admin")
async def admin(request: Request) -> dict:
    body = await request.json()
    if str(body.get("owner_id")) != os.environ.get("TELEGRAM_OWNER_ID", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    command = body.get("command", "").strip()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if command == "/customers":
        rows = conn.execute("SELECT customer_id, email, status, phone, created_at FROM customers ORDER BY created_at DESC").fetchall()
        conn.close()
        lines = [f"{r['customer_id']} | {r['email']} | {r['status']} | {r['phone']}" for r in rows]
        return {"result": "\n".join(lines) or "No customers yet"}
    elif command == "/revenue":
        count = conn.execute("SELECT COUNT(*) FROM customers WHERE status='active'").fetchone()[0]
        conn.close()
        return {"result": f"{count} active customers — ${count * 299}/mo MRR"}
    conn.close()
    return {"result": f"Unknown command: {command}"}
```

---

### Task 4 — PayPal IP allowlist

At the top of the `/paypal-ipn` handler, add:

```python
import ipaddress

PAYPAL_IP_RANGES = [
    ipaddress.ip_network("64.4.240.0/21"),
    ipaddress.ip_network("212.112.232.0/21"),
    ipaddress.ip_network("173.0.80.0/20"),
]

def is_paypal_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in PAYPAL_IP_RANGES)
    except ValueError:
        return False
```

In the handler, add before processing:

```python
client_ip = request.client.host if request.client else ""
if not is_paypal_ip(client_ip):
    logger.warning(f"Rejected PayPal IPN from non-PayPal IP: {client_ip}")
    raise HTTPException(status_code=403, detail="Forbidden")
```

Verify: `python3 -c "import ast; ast.parse(open('scripts/control_plane.py').read()); print('Syntax OK')"`

---

### Sprint 3 Complete

Run tests and report.

---

## Sprint 4 — Infrastructure & Monitoring

*Deploy script, health monitoring, cron jobs.*

### Task 1 — Create scripts/deploy.sh

Create `scripts/deploy.sh`:

```bash
#!/usr/bin/env bash
# Usage: ./deploy.sh <your-domain.com> <your@email.com>
set -euo pipefail

DOMAIN="${1:?Usage: ./deploy.sh <domain> <email>}"
EMAIL="${2:?Usage: ./deploy.sh <domain> <email>}"
REPO="https://github.com/yourusername/hermes-agent.git"  # UPDATE THIS
INSTALL_DIR="/opt/hermes-control-plane"

echo "==> Installing dependencies"
apt-get update -qq
apt-get install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx git

echo "==> Cloning repo"
if [ -d "$INSTALL_DIR" ]; then
    git -C "$INSTALL_DIR" pull
else
    git clone "$REPO" "$INSTALL_DIR"
fi

echo "==> Setting up venv"
cd "$INSTALL_DIR"
python3.11 -m venv venv
venv/bin/pip install -q -r requirements.txt

echo "==> Creating systemd service"
cat > /etc/systemd/system/hermes-control-plane.service << EOF
[Unit]
Description=Hermes AI Employee Control Plane
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python scripts/control_plane.py
EnvironmentFile=$INSTALL_DIR/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hermes-control-plane

echo "==> Creating nginx config"
cat > /etc/nginx/sites-available/hermes-control-plane << EOF
server {
    listen 80;
    server_name $DOMAIN;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/hermes-control-plane /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo "==> Obtaining SSL certificate"
certbot --nginx -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive

echo "==> Starting service"
systemctl start hermes-control-plane
systemctl status hermes-control-plane

echo ""
echo "✅ Deployed! Control plane running at https://$DOMAIN"
echo "Next: copy your .env file to $INSTALL_DIR/.env and restart: systemctl restart hermes-control-plane"
```

`chmod +x scripts/deploy.sh`

---

### Task 2 — Create scripts/health_monitor.py

```python
#!/usr/bin/env python3
"""
VM Health Monitor — runs as a Hermes cron job every 15 minutes.
Pings all active customer VMs and sends Telegram alerts if any are down.
"""
import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".hermes" / "customers.db"
STATE_PATH = Path.home() / ".hermes" / "vm_health.json"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = os.environ.get("TELEGRAM_OWNER_ID", "")
HEALTH_PORT = 8765


def send_telegram(msg: str) -> None:
    if not BOT_TOKEN or not OWNER_ID:
        print(f"[health] {msg}")
        return
    import urllib.parse
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage?chat_id={OWNER_ID}&text={urllib.parse.quote(msg)}"
    try:
        urllib.request.urlopen(url, timeout=10)
    except Exception as e:
        print(f"[health] Telegram send failed: {e}")


def ping_vm(ip: str) -> bool:
    try:
        req = urllib.request.Request(f"http://{ip}:{HEALTH_PORT}/health")
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def main() -> None:
    if not DB_PATH.exists():
        print("[health] No customers DB yet. Nothing to monitor.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    customers = conn.execute(
        "SELECT customer_id, ip FROM customers WHERE status='active' AND ip != ''"
    ).fetchall()
    conn.close()

    if not customers:
        print("[health] No active customers with IPs.")
        return

    state = load_state()
    now = datetime.now(timezone.utc).isoformat()

    for row in customers:
        cid = row["customer_id"]
        ip = row["ip"]
        was_down = state.get(cid, {}).get("down", False)
        is_up = ping_vm(ip)

        if not is_up and not was_down:
            send_telegram(f"🔴 AI Employee DOWN\nCustomer: {cid}\nIP: {ip}\nTime: {now}")
            state[cid] = {"down": True, "since": now}
        elif is_up and was_down:
            since = state.get(cid, {}).get("since", "unknown")
            send_telegram(f"🟢 AI Employee RECOVERED\nCustomer: {cid}\nIP: {ip}\nWas down since: {since}")
            state[cid] = {"down": False}
        else:
            state.setdefault(cid, {})["last_check"] = now

    save_state(state)
    print(f"[health] Checked {len(customers)} VMs. State saved.")


if __name__ == "__main__":
    main()
```

---

### Task 3 — Register cron jobs in Hermes

Using the `cronjob` tool, register these two jobs:

**VM Health Monitor:**
- name: `vm-health-monitor`
- schedule: `*/15 * * * *`
- prompt: `Run the health monitor script: cd ~/Desktop/my\ projects/hermes/hermes-agent && venv/bin/python scripts/health_monitor.py`
- deliver: `telegram`
- model: `claude-haiku-4-5-20251001`

**Daily Revenue Report:**
- name: `daily-revenue-report`
- schedule: `0 9 * * *`
- prompt: `Query the SQLite DB: sqlite3 ~/.hermes/customers.db "SELECT COUNT(*) FROM customers WHERE status='active';" Then calculate MRR = count * 299. Send to Telegram: "📊 Daily Report: {N} active customers — ${MRR}/mo MRR"`
- deliver: `telegram`
- model: `claude-haiku-4-5-20251001`

Verify with: `cronjob action=list`

---

### Sprint 4 Complete

Report all tasks ✅ or ❌.

---

## Sprint 5 — Deploy & Launch

### Task 1 — Create scripts/.env.example

```bash
# ============================================================
# AI Employee Control Plane — Required Environment Variables
# Copy to /opt/hermes-control-plane/.env and fill in values
# ============================================================

# Control Plane
PAYPAL_WEBHOOK_ID=        # From PayPal developer dashboard > Webhooks
TELEGRAM_BOT_TOKEN=       # From @BotFather — for control plane notifications
TELEGRAM_OWNER_ID=        # Your Telegram numeric user ID (use @userinfobot)
CONTROL_PLANE_PORT=8080
CONTROL_PLANE_URL=        # https://yourdomain.com (no trailing slash)

# DigitalOcean VM Provisioning
DO_API_TOKEN=             # DigitalOcean API token (read+write)
DO_SSH_KEY_ID=            # SSH key fingerprint in DO account
DO_REGION=nyc3            # DO datacenter region

# Voice (Vapi.ai)
VAPI_API_KEY=             # Vapi private key
VAPI_WEBHOOK_SECRET=      # Secret from ~/.hermes/.webhook_secret

# Avatar (HeyGen)
HEYGEN_API_KEY=
HEYGEN_AVATAR_ID=         # Avatar template ID in HeyGen dashboard
HEYGEN_VOICE_ID=          # Voice ID

# SMS (Twilio)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=       # E.164 format: +14155551234

# AI (Anthropic — injected into each customer VM)
CLAUDE_CODE_OAUTH_TOKEN=  # Anthropic API key
```

### Task 2 — Deploy landing page to Cloudflare Pages

```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
npx wrangler pages deploy website/ --project-name ai-employee --branch main
```

If wrangler is not installed: `npm install -g wrangler && wrangler login`

Show the deployed URL.

---

### Task 3 — End-to-end smoke test

Start the control plane:
```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN TELEGRAM_OWNER_ID=$TELEGRAM_OWNER_ID PAYPAL_WEBHOOK_ID=test venv/bin/python scripts/control_plane.py &
sleep 2
curl http://localhost:8080/health
```

Simulate a PayPal IPN:
```bash
curl -s -X POST http://localhost:8080/paypal-ipn \
  -d "payment_status=Completed&payer_id=TEST123&payer_email=test@example.com&custom=test-customer-smoke-001&mc_gross=299.00"
```

Verify:
1. Health check returns `{"status": "ok"}`
2. IPN creates row in `~/.hermes/customers.db`
3. Telegram bot sends onboarding message (check phone)

```bash
sqlite3 ~/.hermes/customers.db "SELECT * FROM customers;"
```

Report: PASS or FAIL with logs.

---

### Task 4 — Final commit

```bash
cd ~/Desktop/my\ projects/hermes/hermes-agent
git add scripts/ website/ skills/
git status
git commit -m "feat(ai-employee): production hardening — SQLite, health monitor, deploy script, Vapi phone auto-provisioning, onboarding error handling"
```

---

## Sprint 5 Complete — Product is Live

✅ Landing page deployed and accepting PayPal payments
✅ Control plane running with SQLite + admin commands
✅ Customer onboarding bot with error handling
✅ VM provisioning with Vapi phone auto-buy
✅ Health monitoring every 15 minutes
✅ Daily revenue reports to Telegram

**Next customer signs up → PayPal fires webhook → Telegram interviews them → VM spins up → AI employee is live in ~2 min.**
