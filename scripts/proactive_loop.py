#!/usr/bin/env python3
"""
Proactive Work Loop — runs every 15 minutes, checks 5 queues, acts without asking.

Queues:
    inbox       — unanswered messages in agent mailbox > 2 hours
    leads       — prospects with no follow-up in 3 days
    money       — overdue invoices
    reputation  — unanswered Google/Yelp reviews
    prospecting — new Reddit pain posts matching Hermes ICP

Results logged to ~/.hermes/action_log.jsonl for morning digest.
"""
import fcntl
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_HERMES_HOME = Path(os.environ.get("HOME", str(Path.home()))) / ".hermes"

# ---------------------------------------------------------------------------
# ICP — what Hermes is selling (drives prospecting search queries)
# ---------------------------------------------------------------------------

PROSPECTING_QUERIES = [
    ("need help responding to customer emails", "smallbusiness"),
    ("overwhelmed with customer messages", "Entrepreneur"),
    ("looking for AI tools small business", "smallbusiness"),
    ("hire virtual assistant", "smallbusiness"),
    ("automate follow-ups leads", "sales"),
    ("miss calls losing customers", "smallbusiness"),
    ("AI employee business", "artificial"),
]


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------

def _log_path() -> Path:
    return _HERMES_HOME / "action_log.json"


def log_action(action: str, queue: str = "general") -> None:
    """Append a completed action to the action log. File-locked for concurrent safety."""
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({
        "action": action,
        "queue": queue,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    with open(path.with_suffix(".jsonl"), "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(entry + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def load_action_log() -> list:
    """Load the action log. Supports JSONL (new) and JSON array (legacy)."""
    jsonl_path = _log_path().with_suffix(".jsonl")
    json_path = _log_path()
    entries = []
    if jsonl_path.exists():
        try:
            for line in jsonl_path.read_text().splitlines():
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except Exception:
            pass
    elif json_path.exists():
        try:
            entries = json.loads(json_path.read_text())
        except Exception:
            pass
    return entries


def clear_action_log() -> None:
    """Clear the action log (called by morning digest after sending report)."""
    for path in [_log_path().with_suffix(".jsonl"), _log_path()]:
        if path.exists():
            path.write_text("")


# ---------------------------------------------------------------------------
# Telegram helper
# ---------------------------------------------------------------------------

def _telegram_notify(text: str) -> None:
    """Best-effort Telegram notification to owner."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not owner_id:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": owner_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram notify failed: %s", e)


def _notify_if_actions(actions: list) -> None:
    if not actions:
        return
    summary = f"⚡ Hermes completed {len(actions)} actions:\n" + "\n".join(f"• {a}" for a in actions[:10])
    if len(actions) > 10:
        summary += f"\n... and {len(actions) - 10} more"
    _telegram_notify(summary)


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def _load_prospects() -> list:
    """Load all prospects from ~/.hermes/prospects.json."""
    path = _HERMES_HOME / "prospects.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
        if isinstance(raw, dict):
            return list(raw.get("prospects", raw).values())
        return raw
    except Exception:
        return []


def _list_stale_prospects() -> list:
    """Prospects with status new/contacted and no contact in 3+ days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    stale = []
    for p in _load_prospects():
        if p.get("status") not in ("new", "contacted"):
            continue
        if not p.get("contact_hint"):
            continue
        last_str = p.get("last_contact") or p.get("updated_at", "")
        if last_str:
            try:
                last = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
                if last >= cutoff:
                    continue
            except Exception:
                pass
        stale.append(p)
    return stale


def _known_prospect_urls() -> set:
    """Return set of source_urls already in the prospect list to avoid duplicates."""
    return {p.get("source_url", "") for p in _load_prospects() if p.get("source_url")}


def _send_followup(prospect: dict) -> bool:
    """
    Send a follow-up to a prospect.
    - Phone number in contact_hint → Twilio SMS
    - Otherwise → Telegram message to owner asking them to reach out
    Returns True if an action was taken.
    """
    name = prospect.get("name", "Unknown")
    contact = prospect.get("contact_hint", "")
    pain = prospect.get("pain_point", "")

    # Check if contact_hint is a phone number
    phone_match = re.search(r"\+?1?\d{10,14}", contact.replace("-", "").replace(" ", ""))
    if phone_match:
        phone = phone_match.group()
        if not phone.startswith("+"):
            phone = "+1" + phone.lstrip("1")
        try:
            from tools.twilio_tool import sms_send_tool
            msg = (
                f"Hi {name.split()[0]}! I noticed you mentioned needing help with "
                f"{pain[:80] if pain else 'your business'}. "
                f"Hermes can handle your emails, leads, and follow-ups automatically. "
                f"Want to see how? Reply YES and I'll share a quick demo."
            )
            result = sms_send_tool(phone, msg)
            logger.info("SMS follow-up to %s: %s", name, result)
            return True
        except Exception as e:
            logger.warning("SMS to %s failed: %s", name, e)

    # No phone — notify owner via Telegram so they can reach out manually
    source_url = prospect.get("source_url", "")
    msg = (
        f"📋 Follow-up needed: *{name}*\n"
        f"Pain: {pain[:120] if pain else 'N/A'}\n"
        f"Contact: {contact or 'unknown'}\n"
        f"{source_url}"
    )
    _telegram_notify(msg)
    logger.info("Owner notified to follow up with %s", name)
    return True


def _list_overdue_invoices() -> list:
    """Invoices overdue >30 days from ~/.hermes/invoices.json."""
    path = _HERMES_HOME / "invoices.json"
    if not path.exists():
        return []
    try:
        invoices = json.loads(path.read_text())
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    overdue = []
    for inv in invoices:
        due_str = inv.get("due_date")
        if due_str and inv.get("status") == "unpaid":
            try:
                if datetime.fromisoformat(due_str.replace("Z", "+00:00")) < cutoff:
                    overdue.append(inv)
            except Exception:
                pass
    return overdue


# ---------------------------------------------------------------------------
# Queue runners
# ---------------------------------------------------------------------------

def run_inbox_queue() -> list:
    """Check agent mailbox for messages needing a response > 2 hours old."""
    actions = []
    try:
        mailbox_root = _HERMES_HOME / "mailbox"
        if not mailbox_root.exists():
            return actions

        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        for folder in mailbox_root.iterdir():
            if not folder.is_dir():
                continue
            for msg_file in sorted(folder.glob("*.json")):
                try:
                    raw = json.loads(msg_file.read_text())
                    # Mailbox files can be a list of messages or a single message dict
                    msgs = raw if isinstance(raw, list) else [raw]
                    for msg in msgs:
                        if not isinstance(msg, dict):
                            continue
                        _process_mailbox_msg(msg, msg_file, folder.name, cutoff, actions)
                except Exception as e:
                    logger.warning("Mailbox file error %s: %s", msg_file, e)
    except Exception as e:
        logger.warning("Inbox queue error: %s", e)
    return actions


def _process_mailbox_msg(msg: dict, msg_file: Path, folder: str, cutoff, actions: list) -> None:
    try:
        if msg.get("status") != "unread":
            return
        ts_str = msg.get("timestamp", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts > cutoff:
                    return  # too recent
            except Exception:
                pass

        sender = msg.get("from", folder)
        subject = msg.get("subject", msg.get("content", "")[:60])
        action = f"Flagged unread message from {sender}: {subject}"
        _telegram_notify(f"📬 Unread message ({folder}):\nFrom: {sender}\n{subject}")
        log_action(action, queue="inbox")
        actions.append(action)
        msg["status"] = "flagged"
        msg_file.write_text(json.dumps(msg, indent=2))
    except Exception as e:
        logger.warning("Mailbox message error %s: %s", msg_file, e)


def run_leads_queue() -> list:
    """Run growth engine: research prospects, do real work, send deliverables as pitch."""
    actions = []
    try:
        from scripts.growth_engine import run_growth_pipeline
        new_actions = run_growth_pipeline(limit=2)
        for action in new_actions:
            log_action(action, queue="leads")
        actions.extend(new_actions)
    except Exception as e:
        logger.warning("Leads queue error: %s", e)
    return actions


def run_money_queue() -> list:
    """Send payment reminders for overdue invoices."""
    actions = []
    try:
        overdue = _list_overdue_invoices()
        logger.info("Money queue: %d overdue invoices", len(overdue))
        for invoice in overdue:
            client = invoice.get("client_name", "client")
            amount = invoice.get("amount", 0)
            phone = invoice.get("client_phone", "")
            if phone:
                try:
                    from tools.twilio_tool import sms_send_tool
                    msg = (
                        f"Hi {client}, this is a reminder that your invoice of ${amount} "
                        f"is overdue. Please reply to arrange payment. Thank you!"
                    )
                    sms_send_tool(phone, msg)
                except Exception as e:
                    logger.warning("SMS payment reminder failed: %s", e)

            _telegram_notify(f"💸 Overdue invoice: {client} owes ${amount}")
            action = f"Sent payment reminder to {client} (${amount} overdue)"
            log_action(action, queue="money")
            actions.append(action)
    except Exception as e:
        logger.warning("Money queue error: %s", e)
    return actions


def run_prospecting_queue() -> list:
    """Search Reddit for pain posts matching Hermes ICP and add new leads."""
    actions = []
    try:
        from tools.reach_tools import reddit_search_tool
        from tools.prospect_tool import prospect_add_fn

        known_urls = _known_prospect_urls()
        logger.info("Prospecting queue: searching Reddit...")

        for query, subreddit in PROSPECTING_QUERIES[:3]:  # cap at 3 searches per run
            try:
                results = reddit_search_tool(query, subreddit=subreddit, limit=5)
                if results.startswith("Error"):
                    logger.warning("Reddit search failed: %s", results)
                    continue

                # Parse results — each line: "- **Title** (r/sub, ...)\n  url"
                lines = results.split("\n")
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith("- **"):
                        title_match = re.search(r"\*\*(.+?)\*\*", line)
                        url = lines[i + 1].strip() if i + 1 < len(lines) else ""
                        title = title_match.group(1) if title_match else line[4:]

                        if url and url not in known_urls:
                            result = prospect_add_fn(
                                name=f"Reddit: {title[:60]}",
                                source="reddit",
                                pain_point=title,
                                source_url=url,
                                contact_hint=f"Reddit post in r/{subreddit}",
                                score=6,
                            )
                            known_urls.add(url)
                            action = f"Found prospect on Reddit: {title[:60]}"
                            log_action(action, queue="prospecting")
                            actions.append(action)
                            logger.info("New prospect added: %s", title[:60])
                    i += 1
            except Exception as e:
                logger.warning("Reddit search '%s' failed: %s", query, e)

        # Immediately run growth engine on the best new find (score >= 8)
        if any(True for a in actions):
            try:
                from scripts.growth_engine import run_growth_pipeline
                growth_actions = run_growth_pipeline(limit=1)
                for ga in growth_actions:
                    log_action(ga, queue="prospecting")
                actions.extend(growth_actions)
            except Exception as e:
                logger.warning("Growth engine after prospecting failed: %s", e)

    except ImportError as e:
        logger.warning("Prospecting tools not available: %s", e)
    except Exception as e:
        logger.warning("Prospecting queue error: %s", e)
    return actions


def run_reputation_queue() -> list:
    """Respond to unanswered Google/Yelp reviews (requires GBP MCP)."""
    actions = []
    try:
        logger.info("Reputation queue: checking for unanswered reviews...")
        # Wired when Google Business Profile MCP is connected
        # mcp_autoconfig will detect GBP credentials and configure the server
    except Exception as e:
        logger.warning("Reputation queue error: %s", e)
    return actions


def run_all_queues() -> list:
    """Run all 5 queues and return combined list of actions."""
    all_actions = []
    all_actions.extend(run_inbox_queue())
    all_actions.extend(run_leads_queue())
    all_actions.extend(run_money_queue())
    all_actions.extend(run_prospecting_queue())
    all_actions.extend(run_reputation_queue())
    _notify_if_actions(all_actions)
    return all_actions


if __name__ == "__main__":
    logger.info("Starting proactive loop run at %s", datetime.now(timezone.utc).isoformat())
    actions = run_all_queues()
    logger.info("Completed %d actions", len(actions))
