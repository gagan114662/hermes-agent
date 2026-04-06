#!/usr/bin/env python3
"""
Provision a new customer VM on DigitalOcean.

Usage:
    python scripts/provision_vm.py --customer-id <id> --config customer_config.json

Environment:
    DO_API_TOKEN  — DigitalOcean API token
    DO_SSH_KEY_ID — SSH key ID already added to DigitalOcean account
    DO_REGION     — Region (default: nyc3)
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import httpx

DO_BASE = "https://api.digitalocean.com/v2"
HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"


def buy_vapi_phone(vapi_api_key: str, area_code: str = "415") -> dict:
    """Purchase a Vapi phone number for a new customer. Returns {id, number}."""
    payload = json.dumps({"provider": "twilio", "areaCode": area_code}).encode()
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
        data = json.loads(resp.read())
    return {"id": data.get("id", ""), "number": data.get("number", "")}


def _do_headers():
    return {
        "Authorization": f"Bearer {os.environ['DO_API_TOKEN']}",
        "Content-Type": "application/json",
    }


CLOUD_INIT_TEMPLATE = """#!/bin/bash
set -e
apt-get update -qq
apt-get install -y -qq git curl python3.11 python3.11-venv nodejs npm nginx
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
git clone {hermes_repo} /opt/hermes
cd /opt/hermes
./setup-hermes.sh
cat > /opt/hermes/.env << 'ENVEOF'
{env_content}
ENVEOF
mkdir -p /root/.hermes
cat > /root/.hermes/config.yaml << 'CFGEOF'
{hermes_config}
CFGEOF
npm install -g openwork-orchestrator
npm install -g @steipete/bird
npm install -g @page-agent/mcp
# Install Ollama (local LLM — no API key required)
curl -fsSL https://ollama.com/install.sh | sh
systemctl enable ollama
systemctl start ollama
sleep 10
ollama pull gemma3:4b
cat > /etc/systemd/system/hermes-gateway.service << 'SVCEOF'
[Unit]
Description=Hermes Gateway
After=network.target ollama.service
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

    env_lines = [
        f"HERMES_INFERENCE_PROVIDER=ollama",
        f"TELEGRAM_BOT_TOKEN={customer_config.get('telegram_token', '')}",
        f"TWILIO_ACCOUNT_SID={customer_config.get('twilio_sid', '')}",
        f"TWILIO_AUTH_TOKEN={customer_config.get('twilio_token', '')}",
        f"TWILIO_PHONE_NUMBER={customer_config.get('twilio_number', '')}",
        f"CUSTOMER_ID={customer_id}",
        f"BUSINESS_NAME={customer_config.get('business_name', '')}",
        f"CONTROL_PLANE_URL={os.environ.get('CONTROL_PLANE_URL', '')}",
        f"VAPI_WEBHOOK_SECRET={os.environ.get('VAPI_WEBHOOK_SECRET', '')}",
        f"PAYPAL_WEBHOOK_ID={os.environ.get('PAYPAL_WEBHOOK_ID', '')}",
        # Booking (Cal.com)
        f"CALCOM_API_KEY={customer_config.get('calcom_api_key', '')}",
        f"CALCOM_EVENT_ID={customer_config.get('calcom_event_id', '')}",
        # Invoicing (Crater)
        f"CRATER_BASE_URL={customer_config.get('crater_base_url', '')}",
        f"CRATER_API_TOKEN={customer_config.get('crater_api_token', '')}",
        f"CRATER_COMPANY_ID={customer_config.get('crater_company_id', '')}",
        # Email marketing (Mautic)
        f"MAUTIC_BASE_URL={customer_config.get('mautic_base_url', '')}",
        f"MAUTIC_USERNAME={customer_config.get('mautic_username', '')}",
        f"MAUTIC_PASSWORD={customer_config.get('mautic_password', '')}",
        # WhatsApp via Twilio (paid)
        f"TWILIO_WHATSAPP_NUMBER={customer_config.get('twilio_whatsapp_number', '')}",
        # WhatsApp via Evolution API (free, self-hosted)
        f"EVOLUTION_API_URL={customer_config.get('evolution_api_url', os.environ.get('EVOLUTION_API_URL', ''))}",
        f"EVOLUTION_API_KEY={customer_config.get('evolution_api_key', os.environ.get('EVOLUTION_API_KEY', ''))}",
        f"EVOLUTION_INSTANCE={customer_config.get('evolution_instance', 'default')}",
        # Voice via Fonoster (free, self-hosted)
        f"FONOSTER_ACCESS_KEY_ID={customer_config.get('fonoster_key_id', os.environ.get('FONOSTER_ACCESS_KEY_ID', ''))}",
        f"FONOSTER_ACCESS_KEY_SECRET={customer_config.get('fonoster_key_secret', os.environ.get('FONOSTER_ACCESS_KEY_SECRET', ''))}",
        f"FONOSTER_APP_REF={customer_config.get('fonoster_app_ref', os.environ.get('FONOSTER_APP_REF', ''))}",
        f"FONOSTER_FROM_NUMBER={customer_config.get('fonoster_from_number', '')}",
        f"FONOSTER_API_URL={customer_config.get('fonoster_api_url', os.environ.get('FONOSTER_API_URL', ''))}",
        # SMS via Android gateway (free)
        f"ANDROID_SMS_GATEWAY_URL={customer_config.get('android_sms_url', os.environ.get('ANDROID_SMS_GATEWAY_URL', ''))}",
        f"ANDROID_SMS_GATEWAY_USER={customer_config.get('android_sms_user', 'user')}",
        f"ANDROID_SMS_GATEWAY_PASSWORD={customer_config.get('android_sms_password', os.environ.get('ANDROID_SMS_GATEWAY_PASSWORD', ''))}",
        # Easy!Appointments booking (free, self-hosted)
        f"EASYAPP_URL={customer_config.get('easyapp_url', os.environ.get('EASYAPP_URL', ''))}",
        f"EASYAPP_USERNAME={customer_config.get('easyapp_username', os.environ.get('EASYAPP_USERNAME', ''))}",
        f"EASYAPP_PASSWORD={customer_config.get('easyapp_password', os.environ.get('EASYAPP_PASSWORD', ''))}",
    ]

    hermes_config = (
        f"model:\n"
        f"  default: gemma3:4b\n"
        f"  provider: ollama\n"
        f"  base_url: 'http://localhost:11434'\n"
        f"  api_key: 'ollama'\n"
        f"fallback_providers: []\n"
        f"fallback_model: {{}}\n"
        f"mcp_servers:\n"
        f"  page-agent:\n"
        f"    command: /usr/local/bin/page-agent-mcp\n"
        f"    args: []\n"
        f"    env:\n"
        f"      LLM_MODEL_NAME: gemma3:4b\n"
        f"      LLM_API_KEY: ollama\n"
        f"      LLM_BASE_URL: 'http://localhost:11434/v1'\n"
        f"agent:\n"
        f"  name: \"{customer_config.get('agent_name', 'Alex')}\"\n"
        f"  personality: \"{customer_config.get('personality', 'professional and helpful')}\"\n"
        f"  business_context: |\n"
        f"    Business: {customer_config.get('business_name', '')}\n"
        f"    Industry: {customer_config.get('industry', '')}\n"
        f"    What we sell: {customer_config.get('product', '')}\n"
        f"    Target customer: {customer_config.get('target_customer', '')}\n"
        f"    Tone: {customer_config.get('tone', 'professional')}\n"
    )

    cloud_init = CLOUD_INIT_TEMPLATE.format(
        hermes_repo=HERMES_REPO,
        env_content="\n".join(env_lines),
        hermes_config=hermes_config,
    )

    payload = {
        "name": f"hermes-agent-{customer_id}",
        "region": region,
        "size": "s-2vcpu-4gb",
        "image": "ubuntu-22-04-x64",
        "ssh_keys": [ssh_key_id] if ssh_key_id else [],
        "user_data": cloud_init,
        "tags": ["hermes-agent", f"customer-{customer_id}"],
    }

    resp = httpx.post(f"{DO_BASE}/droplets", headers=_do_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    droplet = resp.json()["droplet"]
    droplet_id = droplet["id"]

    print(f"Droplet {droplet_id} created. Waiting for IP...")

    for _ in range(30):
        time.sleep(5)
        r = httpx.get(f"{DO_BASE}/droplets/{droplet_id}", headers=_do_headers(), timeout=15)
        r.raise_for_status()
        d = r.json()["droplet"]
        networks = d.get("networks", {}).get("v4", [])
        public_ips = [n["ip_address"] for n in networks if n["type"] == "public"]
        if public_ips:
            ip = public_ips[0]

            # Auto-provision Vapi phone number
            vapi_key = customer_config.get("vapi_api_key") or os.environ.get("VAPI_API_KEY", "")
            vapi_phone: dict = {}
            if vapi_key:
                try:
                    vapi_phone = buy_vapi_phone(vapi_key)
                    # Patch the .env on the VM with the real phone ID
                    env_lines.append(f"VAPI_PHONE_ID={vapi_phone.get('id', '')}")
                    env_lines.append(f"VAPI_PHONE_NUMBER={vapi_phone.get('number', '')}")
                    print(f"Vapi phone provisioned: {vapi_phone.get('number')}")
                except Exception as e:
                    print(f"Warning: Vapi phone provisioning failed (non-fatal): {e}")

            return {
                "droplet_id": droplet_id,
                "ip": ip,
                "customer_id": customer_id,
                "status": "provisioning",
                "vapi_phone_number": vapi_phone.get("number", ""),
                "vapi_phone_id": vapi_phone.get("id", ""),
            }

    raise TimeoutError("VM did not get an IP within 150 seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    with open(args.config) as f:
        config = json.load(f)
    result = provision_vm(args.customer_id, config)
    print(json.dumps(result, indent=2))
