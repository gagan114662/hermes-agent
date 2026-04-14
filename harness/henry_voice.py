"""Henry's voice and text briefing system.

Handles:
- Collecting the day's work from team_updates.jsonl
- Making outbound Vapi calls with a structured briefing
- Sending Telegram/WhatsApp fallback when Vapi is unavailable
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_HERMES_HOME = Path.home() / ".hermes"
_EXPERIMENTS_DIR = _HERMES_HOME / "experiments"


# ── Data collection ───────────────────────────────────────────────────────────

async def compile_daily_briefing(hours: int = 24) -> dict:
    """Collect the day's work from team_updates.jsonl and experiment results.

    Parameters
    ----------
    hours : How far back to look (default 24h).

    Returns
    -------
    Structured briefing dict ready for voice script generation or text formatting.
    """
    from gateway.team_chat import load_updates

    updates = load_updates(hours=hours)

    # Group updates by employee
    by_employee: dict[str, list[str]] = {}
    for u in updates:
        emp = u.get("employee", "unknown")
        if emp == "henry":
            continue  # Skip Henry's own posts
        msg = u.get("message", "")
        if msg:
            by_employee.setdefault(emp, []).append(msg)

    # Scan experiment results for wins/blockers
    wins: list[str] = []
    blockers: list[str] = []
    total_actions = sum(len(msgs) for msgs in by_employee.values())

    if _EXPERIMENTS_DIR.exists():
        import json
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        for exp_file in _EXPERIMENTS_DIR.glob("*.jsonl"):
            try:
                for line in exp_file.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    ts_raw = entry.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue
                    except Exception:
                        pass

                    decision = entry.get("decision", "")
                    hypothesis = entry.get("hypothesis", "")
                    if decision == "kept" and hypothesis:
                        wins.append(hypothesis)
                    elif decision == "discarded" and entry.get("notes"):
                        blockers.append(entry["notes"])
            except Exception:
                continue

    date_str = datetime.now().strftime("%A %B %-d")

    return {
        "date": date_str,
        "total_actions": total_actions,
        "by_employee": by_employee,
        "wins": wins,
        "blockers": blockers,
        "tomorrow_plan": [],
    }


# ── Voice call via Vapi ───────────────────────────────────────────────────────

def _build_voice_script(briefing: dict) -> str:
    """Format briefing as a warm, human-sounding PM voice script."""
    lines = [
        f"Good evening! Here's your daily update from the Hermes team for {briefing['date']}.",
        "",
    ]

    by_emp = briefing.get("by_employee", {})
    if by_emp:
        lines.append("Here's what everyone got done today:")
        for emp, updates in by_emp.items():
            name = emp.replace("_", " ").title()
            # Surface the first two updates to keep the call concise
            summary = "; ".join(updates[:2])
            if len(updates) > 2:
                summary += f" — and {len(updates) - 2} more items"
            lines.append(f"{name}: {summary}.")
    else:
        lines.append("The team was quiet today — no updates logged.")

    wins = briefing.get("wins", [])
    if wins:
        lines.append("")
        lines.append(f"A highlight: {wins[0]}")

    blockers = briefing.get("blockers", [])
    if blockers:
        lines.append("")
        lines.append(f"One thing to flag: {blockers[0]}")

    tomorrow = briefing.get("tomorrow_plan", [])
    if tomorrow:
        lines.append("")
        lines.append("Tomorrow we'll focus on: " + "; ".join(tomorrow[:2]) + ".")

    lines.append("")
    lines.append(
        f"That's all for {briefing['date']}. "
        "You'll hear from me again tomorrow evening. Have a great night!"
    )

    return "\n".join(lines)


async def make_vapi_call(phone_number: str, briefing: dict) -> dict:
    """Make an outbound Vapi call delivering the evening briefing.

    Parameters
    ----------
    phone_number : Owner's phone in E.164 format (e.g. +14155552671).
    briefing     : Structured briefing dict from compile_daily_briefing().

    Returns
    -------
    dict with keys: status, call_id, duration_estimate, error (if any).
    """
    import re

    api_key = os.environ.get("VAPI_API_KEY", "")
    phone_id = os.environ.get("VAPI_PHONE_ID", "")
    assistant_id = os.environ.get("VAPI_ASSISTANT_ID", "")

    if not all([api_key, phone_id, assistant_id]):
        return {
            "status": "error",
            "error": "Missing Vapi credentials (VAPI_API_KEY, VAPI_PHONE_ID, VAPI_ASSISTANT_ID)",
            "call_id": None,
            "duration_estimate": 0,
        }

    # Normalise phone number to E.164
    if not phone_number.startswith("+"):
        digits = re.sub(r"\D", "", phone_number)
        phone_number = f"+1{digits}"

    if not re.match(r"^\+[1-9]\d{1,14}$", phone_number):
        return {
            "status": "error",
            "error": f"Invalid phone number format: {phone_number}",
            "call_id": None,
            "duration_estimate": 0,
        }

    voice_script = _build_voice_script(briefing)

    payload = {
        "phoneNumberId": phone_id,
        "assistantId": assistant_id,
        "customer": {"number": phone_number},
        "assistantOverrides": {
            "firstMessage": voice_script,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.vapi.ai/call/phone",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        call_id = data.get("id")
        logger.info("Vapi call initiated: %s", call_id)

        # Rough estimate: ~30 seconds per employee update, 60s overhead
        n_employees = len(briefing.get("by_employee", {}))
        duration_estimate = 60 + n_employees * 30

        return {
            "status": "initiated",
            "call_id": call_id,
            "duration_estimate": duration_estimate,
        }

    except httpx.HTTPStatusError as exc:
        logger.error("Vapi API error %s: %s", exc.response.status_code, exc.response.text)
        return {
            "status": "error",
            "error": f"Vapi HTTP {exc.response.status_code}",
            "call_id": None,
            "duration_estimate": 0,
        }
    except Exception as exc:
        logger.error("Vapi call failed: %s", exc)
        return {
            "status": "error",
            "error": str(exc),
            "call_id": None,
            "duration_estimate": 0,
        }


# ── Telegram fallback ─────────────────────────────────────────────────────────

def _build_telegram_message(briefing: dict) -> str:
    """Format briefing as a richly formatted Telegram message."""
    lines = [
        f"📊 *Evening Report — {briefing['date']}*",
        "",
    ]

    by_emp = briefing.get("by_employee", {})
    if by_emp:
        lines.append("*What your team did today:*")
        for emp, updates in by_emp.items():
            name = emp.replace("_", " ").title()
            lines.append(f"\n👤 *{name}*")
            for u in updates[:3]:
                lines.append(f"  • {u}")
            if len(updates) > 3:
                lines.append(f"  _…and {len(updates) - 3} more_")
    else:
        lines.append("_No team updates logged today._")

    wins = briefing.get("wins", [])
    if wins:
        lines.append("")
        lines.append("🏆 *Wins*")
        for w in wins[:3]:
            lines.append(f"  • {w}")

    blockers = briefing.get("blockers", [])
    if blockers:
        lines.append("")
        lines.append("⚠️ *Blockers*")
        for b in blockers[:3]:
            lines.append(f"  • {b}")

    lines.append("")
    lines.append("_Reply to ask questions or redirect the team._")

    return "\n".join(lines)


async def send_telegram_briefing(chat_id: str, briefing: dict) -> bool:
    """Send the evening briefing as a formatted Telegram message.

    Parameters
    ----------
    chat_id  : Telegram chat ID (owner DM or group).
    briefing : Structured briefing dict.

    Returns
    -------
    True if sent successfully, False otherwise.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — cannot send Telegram briefing")
        return False

    if not chat_id:
        logger.warning("No Telegram chat_id provided")
        return False

    text = _build_telegram_message(briefing)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            resp.raise_for_status()

        logger.info("Telegram briefing sent to %s", chat_id)
        return True

    except Exception as exc:
        logger.error("Telegram briefing failed: %s", exc)
        return False


# ── Delivery orchestration ────────────────────────────────────────────────────

async def deliver_evening_report(user_contact: str, briefing: dict) -> dict:
    """Deliver the evening briefing via the best available channel.

    Priority:
    1. Vapi outbound call (if VAPI_* env vars set and contact is a phone number)
    2. Telegram message (if TELEGRAM_BOT_TOKEN set)
    3. Save markdown file to ~/.hermes/evening_report_{date}.md

    Parameters
    ----------
    user_contact : Phone number (E.164 or national) or Telegram chat ID.
    briefing     : Structured briefing dict from compile_daily_briefing().

    Returns
    -------
    dict with keys: method_used, status, delivered_at, detail
    """
    delivered_at = datetime.now(timezone.utc).isoformat()
    is_phone = user_contact.lstrip("+").replace("-", "").replace(" ", "").isdigit() and len(
        user_contact.lstrip("+").replace("-", "").replace(" ", "")
    ) >= 7

    # 1. Try Vapi voice call
    vapi_ready = all(
        os.environ.get(k) for k in ("VAPI_API_KEY", "VAPI_PHONE_ID", "VAPI_ASSISTANT_ID")
    )
    if vapi_ready and is_phone:
        result = await make_vapi_call(user_contact, briefing)
        if result["status"] == "initiated":
            return {
                "method_used": "vapi_call",
                "status": "delivered",
                "delivered_at": delivered_at,
                "detail": result,
            }
        logger.warning("Vapi call failed (%s), falling back to Telegram", result.get("error"))

    # 2. Try Telegram
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_owner = os.environ.get("TELEGRAM_OWNER_ID", user_contact if not is_phone else "")
    if telegram_token and telegram_owner:
        ok = await send_telegram_briefing(telegram_owner, briefing)
        if ok:
            return {
                "method_used": "telegram",
                "status": "delivered",
                "delivered_at": delivered_at,
                "detail": {"chat_id": telegram_owner},
            }
        logger.warning("Telegram briefing failed, saving to file")

    # 3. File fallback
    date_slug = datetime.now().strftime("%Y-%m-%d")
    report_path = _HERMES_HOME / f"evening_report_{date_slug}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    voice_script = _build_voice_script(briefing)
    report_path.write_text(
        f"# Evening Report — {briefing['date']}\n\n{voice_script}\n"
    )
    logger.info("Evening report saved to %s", report_path)

    return {
        "method_used": "file",
        "status": "saved",
        "delivered_at": delivered_at,
        "detail": {"path": str(report_path)},
    }
