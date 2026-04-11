"""
Google Workspace Tools — Gmail, Calendar, and Sheets via gogcli (gog CLI).

Tools:
    gmail_search     — Search Gmail messages
    gmail_get        — Get a specific Gmail message
    gmail_send       — Send a new email
    gmail_reply      — Reply to an existing email thread
    calendar_list    — List upcoming calendar events
    calendar_create  — Create a new calendar event
    sheets_get       — Read data from a Google Sheet
    sheets_append    — Append rows to a Google Sheet

Dependencies:
    gogcli  — Install via: brew install gogcli
              Auth setup: gog auth credentials ~/Downloads/client_secret_*.json
                          gog auth add gagan@getfoolish.com
"""

import json
import logging
import os
import shutil
import subprocess
from typing import Optional

from tools.registry import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list, timeout: int = 30) -> tuple:
    """Run a subprocess, return (stdout, stderr, returncode)."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ},
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _gog_available() -> bool:
    return shutil.which("gog") is not None


def _gog_auth_configured() -> bool:
    """Check if gogcli has at least one account configured."""
    if not _gog_available():
        return False
    stdout, _, rc = _run(["gog", "auth", "list"], timeout=5)
    return rc == 0 and bool(stdout.strip())


def _auth_error() -> str:
    return (
        "Error: gogcli not authenticated. Run:\n"
        "  gog auth credentials ~/Downloads/client_secret_*.json\n"
        "  gog auth add gagan@getfoolish.com\n"
        "See ~/.hermes/workspace/TOOLS.md for setup instructions."
    )


def _check_gog() -> tuple:
    if not _gog_available():
        return False, "gogcli (gog) not found. Install via: brew install gogcli"
    if not _gog_auth_configured():
        return False, "gogcli not authenticated. Run: gog auth add gagan@getfoolish.com"
    return True, "gogcli available"


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

def gmail_search_tool(query: str, max_results: int = 20) -> str:
    """Search Gmail messages."""
    stdout, stderr, rc = _run(
        ["gog", "--json", "gmail", "search", query, "--max", str(max_results)],
        timeout=30,
    )
    if rc != 0:
        return f"Error searching Gmail: {stderr or stdout}"
    if not stdout:
        return "No messages found."
    try:
        data = json.loads(stdout)
        if not data:
            return "No messages found."
        lines = []
        for msg in data:
            subject = msg.get("subject", "(no subject)")
            sender = msg.get("from", "unknown")
            date = msg.get("date", "")
            msg_id = msg.get("id", "")
            snippet = msg.get("snippet", "")[:100]
            lines.append(f"[{msg_id}] {date} | From: {sender}\nSubject: {subject}\n{snippet}\n")
        return "\n".join(lines)
    except (json.JSONDecodeError, TypeError):
        return stdout[:2000] if stdout else "No results."


def gmail_get_tool(message_id: str) -> str:
    """Get a specific Gmail message by ID."""
    stdout, stderr, rc = _run(
        ["gog", "--json", "gmail", "get", message_id],
        timeout=20,
    )
    if rc != 0:
        return f"Error getting message {message_id}: {stderr or stdout}"
    return stdout[:3000] if stdout else "Message not found."


def gmail_send_tool(to: str, subject: str, body: str, cc: Optional[str] = None) -> str:
    """Send a new email."""
    cmd = ["gog", "gmail", "send", "--to", to, "--subject", subject, "--body", body]
    if cc:
        cmd += ["--cc", cc]
    stdout, stderr, rc = _run(cmd, timeout=30)
    if rc != 0:
        return f"Error sending email: {stderr or stdout}"
    return f"Email sent to {to}: {subject}"


def gmail_reply_tool(message_id: str, body: str) -> str:
    """Reply to an existing email thread."""
    stdout, stderr, rc = _run(
        ["gog", "gmail", "send",
         "--reply-to-message-id", message_id,
         "--body", body],
        timeout=30,
    )
    if rc != 0:
        return f"Error replying to message {message_id}: {stderr or stdout}"
    return f"Reply sent to message {message_id}."


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def calendar_list_tool(days: int = 7, calendar_id: str = "primary") -> str:
    """List upcoming calendar events."""
    stdout, stderr, rc = _run(
        ["gog", "--json", "calendar", "events", calendar_id, "--days", str(days)],
        timeout=20,
    )
    if rc != 0:
        return f"Error listing calendar: {stderr or stdout}"
    if not stdout:
        return f"No events in the next {days} days."
    try:
        data = json.loads(stdout)
        if not data:
            return f"No events in the next {days} days."
        lines = []
        for event in data:
            summary = event.get("summary", "(no title)")
            start = event.get("start", {})
            start_time = start.get("dateTime") or start.get("date", "")
            attendees = event.get("attendees", [])
            attendee_str = ""
            if attendees:
                names = [a.get("email", "") for a in attendees[:3]]
                attendee_str = f" | with: {', '.join(names)}"
            lines.append(f"• {start_time}: {summary}{attendee_str}")
        return "\n".join(lines)
    except (json.JSONDecodeError, TypeError):
        return stdout[:2000] if stdout else f"No events in the next {days} days."


def calendar_create_tool(
    summary: str,
    start: str,
    end: str,
    attendees: Optional[str] = None,
    calendar_id: str = "primary",
) -> str:
    """Create a new calendar event. start/end in ISO 8601 format."""
    cmd = [
        "gog", "calendar", "create", calendar_id,
        "--summary", summary,
        "--from", start,
        "--to", end,
    ]
    if attendees:
        cmd += ["--attendees", attendees]
    stdout, stderr, rc = _run(cmd, timeout=20)
    if rc != 0:
        return f"Error creating event: {stderr or stdout}"
    return f"Event created: {summary} from {start} to {end}."


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def sheets_get_tool(sheet_id: str, range_: str) -> str:
    """Read data from a Google Sheet range."""
    stdout, stderr, rc = _run(
        ["gog", "--json", "sheets", "get", sheet_id, range_],
        timeout=20,
    )
    if rc != 0:
        return f"Error reading sheet {sheet_id} range {range_}: {stderr or stdout}"
    return stdout[:3000] if stdout else "No data found."


def sheets_append_tool(sheet_id: str, range_: str, data: str) -> str:
    """Append rows to a Google Sheet. data format: 'val1|val2,val3|val4' (| separates cols, , separates rows)."""
    stdout, stderr, rc = _run(
        ["gog", "sheets", "append", sheet_id, range_, data],
        timeout=20,
    )
    if rc != 0:
        return f"Error appending to sheet {sheet_id}: {stderr or stdout}"
    return f"Appended to {sheet_id} range {range_}."


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

registry.register(
    name="gmail_search",
    toolset="google-workspace",
    schema={
        "name": "gmail_search",
        "description": "Search Gmail messages using Gmail search syntax (e.g. 'is:unread newer_than:1d', 'from:someone@example.com subject:meeting'). Returns message IDs, senders, subjects, and snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query (supports full Gmail search syntax)"},
                "max_results": {"type": "integer", "description": "Maximum messages to return (default: 20)", "default": 20},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: gmail_search_tool(args["query"], args.get("max_results", 20)),
    check_fn=_check_gog,
    emoji="📧",
    is_concurrency_safe=True,
)

registry.register(
    name="gmail_get",
    toolset="google-workspace",
    schema={
        "name": "gmail_get",
        "description": "Get the full content of a specific Gmail message by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID (from gmail_search results)"},
            },
            "required": ["message_id"],
        },
    },
    handler=lambda args, **kw: gmail_get_tool(args["message_id"]),
    check_fn=_check_gog,
    emoji="📬",
    is_concurrency_safe=True,
)

registry.register(
    name="gmail_send",
    toolset="google-workspace",
    schema={
        "name": "gmail_send",
        "description": "Send a new email from Gagan's Gmail account.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body (plain text)"},
                "cc": {"type": "string", "description": "CC email address (optional)"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    handler=lambda args, **kw: gmail_send_tool(
        args["to"], args["subject"], args["body"], args.get("cc")
    ),
    check_fn=_check_gog,
    emoji="📤",
    is_concurrency_safe=False,
)

registry.register(
    name="gmail_reply",
    toolset="google-workspace",
    schema={
        "name": "gmail_reply",
        "description": "Reply to an existing Gmail thread by message ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID to reply to"},
                "body": {"type": "string", "description": "Reply body text"},
            },
            "required": ["message_id", "body"],
        },
    },
    handler=lambda args, **kw: gmail_reply_tool(args["message_id"], args["body"]),
    check_fn=_check_gog,
    emoji="↩️",
    is_concurrency_safe=False,
)

registry.register(
    name="calendar_list",
    toolset="google-workspace",
    schema={
        "name": "calendar_list",
        "description": "List upcoming Google Calendar events. Returns event titles, start times, and attendees.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days ahead to look (default: 7)", "default": 7},
                "calendar_id": {"type": "string", "description": "Calendar ID (default: 'primary')", "default": "primary"},
            },
        },
    },
    handler=lambda args, **kw: calendar_list_tool(args.get("days", 7), args.get("calendar_id", "primary")),
    check_fn=_check_gog,
    emoji="📅",
    is_concurrency_safe=True,
)

registry.register(
    name="calendar_create",
    toolset="google-workspace",
    schema={
        "name": "calendar_create",
        "description": "Create a new event on Google Calendar.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Event title"},
                "start": {"type": "string", "description": "Start datetime in ISO 8601 (e.g. 2026-04-03T10:00:00-07:00)"},
                "end": {"type": "string", "description": "End datetime in ISO 8601"},
                "attendees": {"type": "string", "description": "Comma-separated attendee emails (optional)"},
                "calendar_id": {"type": "string", "description": "Calendar ID (default: 'primary')", "default": "primary"},
            },
            "required": ["summary", "start", "end"],
        },
    },
    handler=lambda args, **kw: calendar_create_tool(
        args["summary"], args["start"], args["end"],
        args.get("attendees"), args.get("calendar_id", "primary"),
    ),
    check_fn=_check_gog,
    emoji="📆",
    is_concurrency_safe=False,
)

registry.register(
    name="sheets_get",
    toolset="google-workspace",
    schema={
        "name": "sheets_get",
        "description": "Read data from a Google Sheets range.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {"type": "string", "description": "Google Sheet ID (from the URL)"},
                "range": {"type": "string", "description": "Sheet range in A1 notation (e.g. 'Sheet1!A1:F20')"},
            },
            "required": ["sheet_id", "range"],
        },
    },
    handler=lambda args, **kw: sheets_get_tool(args["sheet_id"], args["range"]),
    check_fn=_check_gog,
    emoji="📊",
    is_concurrency_safe=True,
)

registry.register(
    name="sheets_append",
    toolset="google-workspace",
    schema={
        "name": "sheets_append",
        "description": "Append one or more rows to a Google Sheet. Use pipe-separated columns and comma-separated rows: 'col1|col2,col3|col4'.",
        "parameters": {
            "type": "object",
            "properties": {
                "sheet_id": {"type": "string", "description": "Google Sheet ID"},
                "range": {"type": "string", "description": "Range to append to (e.g. 'Sheet1!A:F')"},
                "data": {"type": "string", "description": "Row data: columns separated by | and rows by comma. E.g. 'Alice|alice@co.com,Bob|bob@co.com'"},
            },
            "required": ["sheet_id", "range", "data"],
        },
    },
    handler=lambda args, **kw: sheets_append_tool(args["sheet_id"], args["range"], args["data"]),
    check_fn=_check_gog,
    emoji="📝",
    is_concurrency_safe=False,
)
