#!/usr/bin/env python3
"""
VM Health Monitor — runs as a Hermes cron job every 15 minutes.
Pings all active customer VMs and sends Telegram alerts if any are down.
"""
import json
import os
import sqlite3
import urllib.request
import urllib.parse
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
