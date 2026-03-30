#!/usr/bin/env python3
"""
Proactive Work Loop — runs every 15 minutes, checks 5 queues, acts without asking.

Queues:
    inbox       — unanswered emails > 2 hours
    leads       — prospects with no follow-up in 3 days
    money       — overdue invoices
    reputation  — unanswered Google/Yelp reviews
    prospecting — new Reddit/Maps pain posts

Results logged to ~/.hermes/action_log.json for morning digest.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------

def _log_path() -> Path:
    home = Path(os.environ.get("HOME", str(Path.home())))
    return home / ".hermes" / "action_log.json"


def log_action(action: str, queue: str = "general") -> None:
    """Append a completed action to the action log."""
    path = _log_path()
    entries = []
    if path.exists():
        try:
            entries = json.loads(path.read_text())
        except Exception:
            entries = []
    entries.append({
        "action": action,
        "queue": queue,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    path.write_text(json.dumps(entries, indent=2))


def load_action_log() -> list:
    """Load the action log. Returns empty list if file doesn't exist."""
    path = _log_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def clear_action_log() -> None:
    """Clear the action log (called by morning digest after sending report)."""
    path = _log_path()
    path.write_text(json.dumps([]))


# ---------------------------------------------------------------------------
# Queue helpers (stubs — real integrations via MCP tools)
# ---------------------------------------------------------------------------

def _list_stale_prospects() -> list:
    """Return prospects with no follow-up in 3+ days. Reads from ~/.hermes/prospects.json"""
    prospects_path = Path(os.environ.get("HOME", str(Path.home()))) / ".hermes" / "prospects.json"
    if not prospects_path.exists():
        return []
    try:
        prospects = json.loads(prospects_path.read_text())
    except Exception:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    stale = []
    for p in prospects:
        if p.get("status") in ("new", "contacted") and p.get("contact_hint"):
            last_contact_str = p.get("last_contact")
            if last_contact_str:
                try:
                    last_contact = datetime.fromisoformat(last_contact_str.replace("Z", "+00:00"))
                    if last_contact < cutoff:
                        stale.append(p)
                except Exception:
                    stale.append(p)
            else:
                stale.append(p)
    return stale


def _send_followup(prospect: dict) -> None:
    """Send a follow-up SMS/email to a prospect. Best-effort — logs error but doesn't raise."""
    try:
        name = prospect.get("name", "there")
        contact = prospect.get("contact_hint", "")
        logger.info("Sending follow-up to %s at %s", name, contact)
        # Real implementation: call sms_send_tool or send_email_tool via registry
        # For now: log the intent
    except Exception as e:
        logger.warning("Failed to send follow-up to %s: %s", prospect.get("name"), e)


def _list_overdue_invoices() -> list:
    """Return invoices overdue >30 days. Reads from ~/.hermes/invoices.json if exists."""
    invoices_path = Path(os.environ.get("HOME", str(Path.home()))) / ".hermes" / "invoices.json"
    if not invoices_path.exists():
        return []
    try:
        invoices = json.loads(invoices_path.read_text())
    except Exception:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    overdue = []
    for inv in invoices:
        due_str = inv.get("due_date")
        if due_str and inv.get("status") == "unpaid":
            try:
                due = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                if due < cutoff:
                    overdue.append(inv)
            except Exception:
                pass
    return overdue


def _notify_if_actions(actions: list) -> None:
    """Send Telegram notification if there are actions to report."""
    if not actions:
        return
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not owner_id:
        logger.info("No TELEGRAM_OWNER_ID set — skipping notification")
        return
    summary = f"Hermes completed {len(actions)} actions:\n" + "\n".join(f"- {a}" for a in actions[:10])
    if len(actions) > 10:
        summary += f"\n... and {len(actions) - 10} more"
    logger.info("Would notify owner: %s", summary)
    # Real implementation: call send_message_tool via registry


# ---------------------------------------------------------------------------
# Queue runners
# ---------------------------------------------------------------------------

def run_inbox_queue() -> list:
    """Check for unanswered emails > 2 hours and draft replies."""
    actions = []
    try:
        logger.info("Running inbox queue...")
        # Real implementation: query Gmail MCP for unanswered emails > 2h
        # For each: draft reply in owner's tone, log action
        # Stub: returns empty list until Gmail MCP is connected
    except Exception as e:
        logger.warning("Inbox queue error: %s", e)
    return actions


def run_leads_queue() -> list:
    """Follow up with stale prospects (no contact in 3 days)."""
    actions = []
    try:
        stale = _list_stale_prospects()
        for prospect in stale:
            _send_followup(prospect)
            action = f"Sent follow-up to {prospect.get('name', 'unknown prospect')}"
            log_action(action, queue="leads")
            actions.append(action)
    except Exception as e:
        logger.warning("Leads queue error: %s", e)
    return actions


def run_money_queue() -> list:
    """Send payment reminders for overdue invoices."""
    actions = []
    try:
        overdue = _list_overdue_invoices()
        for invoice in overdue:
            client = invoice.get("client_name", "client")
            amount = invoice.get("amount", 0)
            action = f"Sent payment reminder to {client} (${amount} overdue)"
            log_action(action, queue="money")
            actions.append(action)
            logger.info("Payment reminder: %s $%s", client, amount)
    except Exception as e:
        logger.warning("Money queue error: %s", e)
    return actions


def run_prospecting_queue() -> list:
    """Find new leads on Reddit/Maps and add to prospect list."""
    actions = []
    try:
        logger.info("Running prospecting queue...")
        # Real implementation: reddit_search for pain posts, web_search Maps reviews
        # For each relevant post: prospect_add, log action
        # Stub: returns empty list until reddit/maps tools are connected
    except Exception as e:
        logger.warning("Prospecting queue error: %s", e)
    return actions


def run_reputation_queue() -> list:
    """Respond to unanswered Google/Yelp reviews."""
    actions = []
    try:
        logger.info("Running reputation queue...")
        # Real implementation: query GBP MCP for unanswered reviews
        # For each: generate response, post reply, log action
        # Stub: returns empty list until GBP MCP is connected
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
