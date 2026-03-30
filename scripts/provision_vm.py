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
import httpx

DO_BASE = "https://api.digitalocean.com/v2"
HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"


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

    hermes_config = (
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
        "size": "s-2vcpu-2gb",
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
            return {
                "droplet_id": droplet_id,
                "ip": public_ips[0],
                "customer_id": customer_id,
                "status": "provisioning",
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
