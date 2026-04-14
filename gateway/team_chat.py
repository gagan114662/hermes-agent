"""Team Chat — WhatsApp/Telegram group UX for employee updates.

This is the "office" experience.  All employees post updates to a shared
feed (~/.hermes/team_updates.jsonl).  This module:

    1. Reads the feed and formats it as a group chat
    2. Broadcasts new updates to the owner's Telegram/WhatsApp
    3. Provides a FastAPI router for the web dashboard
    4. Supports the owner replying to employees (routing to the right one)

The UX feels like a WhatsApp group where your employees are chatting about
work.  Henry is the PM posting standups, other employees post progress.

Usage
-----
    from gateway.team_chat import router as team_chat_router
    app.include_router(team_chat_router)

Or standalone:
    broadcast_update("alex_outreach", "Sent 15 follow-up emails, got 4 replies!")
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_UPDATES_PATH = Path.home() / ".hermes" / "team_updates.jsonl"
_HERMES_HOME = Path.home() / ".hermes"


# ── Core: read/write the shared update feed ──────────────────────────

def load_updates(hours: int = 24, limit: int = 100) -> list[dict]:
    """Load recent team updates from the shared feed.

    Parameters
    ----------
    hours : How far back to look (default 24h).
    limit : Max number of updates to return.

    Returns
    -------
    List of update dicts, newest first.
    """
    if not _UPDATES_PATH.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    updates = []

    for line in _UPDATES_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            if ts >= cutoff:
                updates.append(entry)
        except Exception:
            continue

    # Newest first, capped
    updates.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return updates[:limit]


def post_update(employee_name: str, role: str, message: str,
                channel: str = "team") -> dict:
    """Post an update to the team feed and broadcast to owner.

    Parameters
    ----------
    employee_name : Who's posting.
    role          : Their role (for display).
    message       : The update text.
    channel       : Channel tag (team, henry, alert).

    Returns
    -------
    The created update entry.
    """
    _UPDATES_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "employee": employee_name,
        "role": role,
        "message": message,
        "channel": channel,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(_UPDATES_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Broadcast to Telegram group
    _broadcast_to_telegram(entry)

    return entry


def _broadcast_to_telegram(entry: dict) -> None:
    """Send update to the Telegram team group (or owner DM)."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    # TELEGRAM_TEAM_GROUP_ID is a Telegram group where all employees post
    # Falls back to TELEGRAM_OWNER_ID for DM
    chat_id = os.environ.get("TELEGRAM_TEAM_GROUP_ID", "")
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not chat_id:
        return

    name = entry["employee"].replace("_", " ").title()
    role = entry.get("role", "")
    msg = entry["message"]
    ts = entry.get("timestamp", "")[:16].replace("T", " ")

    text = f"*{name}* ({role})\n{msg}\n_{ts}_"

    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram broadcast failed: %s", e)


def _broadcast_to_whatsapp(entry: dict) -> None:
    """Send update via WhatsApp Evolution API (self-hosted)."""
    api_url = os.environ.get("WHATSAPP_API_URL", "")
    api_key = os.environ.get("WHATSAPP_API_KEY", "")
    group_id = os.environ.get("WHATSAPP_TEAM_GROUP_ID", "")
    if not all([api_url, api_key, group_id]):
        return

    name = entry["employee"].replace("_", " ").title()
    msg = f"*{name}* ({entry.get('role', '')})\n{entry['message']}"

    try:
        import httpx
        httpx.post(
            f"{api_url}/message/sendText/{os.environ.get('WHATSAPP_INSTANCE', 'hermes')}",
            headers={"apikey": api_key},
            json={
                "number": group_id,
                "text": msg,
            },
            timeout=10,
        )
    except Exception as e:
        logger.warning("WhatsApp broadcast failed: %s", e)


# ── Owner interaction: reply routing ─────────────────────────────────

def route_owner_reply(reply_text: str, context_employee: str = None) -> dict:
    """Route the owner's reply to the right employee.

    If the owner replies in the team group, we need to figure out which
    employee they're talking to and relay the message.

    Parameters
    ----------
    reply_text        : What the owner said.
    context_employee  : If known, which employee this is directed at.

    Returns
    -------
    Dict with routing result.
    """
    # If context is known, direct the reply
    if context_employee:
        return _relay_to_employee(context_employee, reply_text)

    # Otherwise, try to figure out from the message
    # Check if message starts with @employee_name
    if reply_text.startswith("@"):
        parts = reply_text.split(" ", 1)
        emp_name = parts[0][1:].lower().replace(" ", "_")
        message = parts[1] if len(parts) > 1 else ""
        return _relay_to_employee(emp_name, message)

    # Default: relay to Henry (the PM handles routing)
    return _relay_to_employee("henry", reply_text)


def _relay_to_employee(employee_name: str, message: str) -> dict:
    """Write a message to an employee's inbox."""
    inbox_dir = _HERMES_HOME / "mailbox" / employee_name
    inbox_dir.mkdir(parents=True, exist_ok=True)

    entry = {
        "from": "owner",
        "content": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "unread",
    }

    inbox_file = inbox_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    inbox_file.write_text(json.dumps(entry, indent=2))

    return {"routed_to": employee_name, "status": "delivered"}


# ── Format for display ───────────────────────────────────────────────

def format_chat_html(updates: list[dict] = None, hours: int = 24) -> str:
    """Render updates as a WhatsApp-style HTML chat.

    Returns HTML string suitable for embedding in the team dashboard.
    """
    if updates is None:
        updates = load_updates(hours=hours)

    # Reverse so oldest first (chat order)
    updates = list(reversed(updates))

    employee_colors = {}
    color_palette = [
        "#25D366", "#34B7F1", "#FF6B6B", "#C084FC",
        "#FB923C", "#22D3EE", "#A3E635", "#F472B6",
    ]

    lines = [
        '<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;'
        'max-width:600px;margin:0 auto;background:#0b141a;color:#e9edef;'
        'padding:16px;border-radius:12px;min-height:400px;">',
        '<div style="text-align:center;padding:8px;border-bottom:1px solid #222d34;'
        'margin-bottom:12px;font-size:14px;color:#8696a0;">'
        '🏢 Hermes Team Chat</div>',
    ]

    for update in updates:
        emp = update.get("employee", "unknown")
        if emp not in employee_colors:
            employee_colors[emp] = color_palette[len(employee_colors) % len(color_palette)]
        color = employee_colors[emp]

        name = emp.replace("_", " ").title()
        role = update.get("role", "")
        msg = update.get("message", "")
        ts = update.get("timestamp", "")[:16].replace("T", " ")

        lines.append(
            f'<div style="background:#202c33;border-radius:8px;padding:8px 12px;'
            f'margin-bottom:8px;border-left:3px solid {color};">'
            f'<div style="font-size:13px;font-weight:600;color:{color};">'
            f'{name} <span style="font-weight:400;color:#8696a0;font-size:11px;">'
            f'{role}</span></div>'
            f'<div style="font-size:14px;margin-top:4px;">{msg}</div>'
            f'<div style="font-size:11px;color:#8696a0;text-align:right;'
            f'margin-top:4px;">{ts}</div></div>'
        )

    if not updates:
        lines.append(
            '<div style="text-align:center;color:#8696a0;padding:40px;">'
            'No team updates yet. Employees will post here when they start working.</div>'
        )

    lines.append('</div>')
    return "\n".join(lines)


# ── FastAPI router ───────────────────────────────────────────────────

def get_router():
    """Create and return the FastAPI router for team chat endpoints."""
    from fastapi import APIRouter
    from fastapi.responses import HTMLResponse, JSONResponse

    router = APIRouter(tags=["team-chat"])

    @router.get("/api/team/chat")
    async def get_chat(hours: int = 24, limit: int = 50):
        """Get recent team updates as JSON."""
        updates = load_updates(hours=hours, limit=limit)
        return JSONResponse(content={"updates": updates})

    @router.get("/team/chat", response_class=HTMLResponse)
    async def chat_page(hours: int = 24):
        """Render the team chat as a WhatsApp-style HTML page."""
        html = f"""<!DOCTYPE html>
<html><head>
<title>Hermes Team Chat</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{margin:0;background:#0b141a;}}</style>
<script>
// Auto-refresh every 10 seconds
setTimeout(() => location.reload(), 10000);
</script>
</head><body>
{format_chat_html(hours=hours)}
</body></html>"""
        return HTMLResponse(content=html)

    @router.post("/api/team/chat/reply")
    async def owner_reply(employee: str = "", message: str = ""):
        """Owner replies to an employee via the chat."""
        result = route_owner_reply(message, context_employee=employee or None)
        return JSONResponse(content=result)

    return router
