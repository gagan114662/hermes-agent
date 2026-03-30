"""
Credential Harvester — reads macOS Keychain and browser saved passwords.

Maps known service domains to service names. Returns structured credential
dicts for use by the MCP auto-configurator. Credentials never leave this
machine — no logging, no network calls.
"""
import re
import sqlite3
import subprocess
import shutil
from pathlib import Path
from typing import Optional

# domain substring → service name
SERVICE_MAP = {
    "gmail.com": "gmail",
    "google.com": "gmail",
    "mail.google.com": "gmail",
    "shopify.com": "shopify",
    "quickbooks.intuit.com": "quickbooks",
    "intuit.com": "quickbooks",
    "stripe.com": "stripe",
    "dashboard.stripe.com": "stripe",
    "calendly.com": "calendly",
    "notion.so": "notion",
    "slack.com": "slack",
    "airtable.com": "airtable",
    "hubspot.com": "hubspot",
    "squareup.com": "square",
    "square.com": "square",
    "xero.com": "xero",
    "trello.com": "trello",
    "github.com": "github",
    "wordpress.com": "wordpress",
    "woocommerce.com": "woocommerce",
}


def _map_domain_to_service(domain: str) -> Optional[str]:
    domain = domain.lower()
    for pattern, service in SERVICE_MAP.items():
        if pattern in domain:
            return service
    return None


def _run_keychain_dump() -> str:
    """Dump all internet passwords from the login keychain."""
    try:
        result = subprocess.run(
            ["security", "dump-keychain", "-d", "login.keychain"],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout
    except Exception:
        return ""


def _parse_keychain_output(raw: str) -> Optional[dict]:
    """Parse a single keychain entry block. Returns None if incomplete."""
    username_match = re.search(r'"acct"<blob>="([^"]+)"', raw)
    domain_match = re.search(r'"srvr"<blob>="([^"]+)"', raw)
    password_match = re.search(r'^password: "([^"]*)"', raw, re.MULTILINE)

    if not (username_match and domain_match and password_match):
        return None

    return {
        "username": username_match.group(1),
        "domain": domain_match.group(1),
        "password": password_match.group(1),
    }


def _read_browser_passwords() -> list:
    """
    Read Chrome saved passwords from its SQLite Login Data file.
    Returns list of {domain, username, password} dicts.
    Note: Chrome must be closed for the DB to be readable.
    """
    results = []
    chrome_path = Path.home() / "Library/Application Support/Google/Chrome/Default/Login Data"
    if not chrome_path.exists():
        return results

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    shutil.copy2(chrome_path, tmp_path)

    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.execute(
            "SELECT origin_url, username_value, password_value FROM logins"
        )
        for url, username, _ in cursor.fetchall():
            domain_match = re.search(r"https?://([^/]+)", url or "")
            if domain_match and username:
                results.append({
                    "domain": domain_match.group(1),
                    "username": username,
                    "password": "",  # encrypted, skip for now
                })
        conn.close()
    except Exception:
        pass
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return results


def harvest_credentials() -> list:
    """
    Harvest credentials from Keychain and browser.
    Returns list of {service, username, password, source} dicts
    for known services only. Unknowns are silently skipped.
    """
    found = []
    seen_services = set()

    raw = _run_keychain_dump()
    entries = re.split(r'(?=keychain:)', raw)
    for entry in entries:
        parsed = _parse_keychain_output(entry)
        if not parsed:
            continue
        service = _map_domain_to_service(parsed["domain"])
        if service and service not in seen_services:
            seen_services.add(service)
            found.append({
                "service": service,
                "username": parsed["username"],
                "password": parsed["password"],
                "source": "keychain",
            })

    for entry in _read_browser_passwords():
        service = _map_domain_to_service(entry["domain"])
        if service and service not in seen_services:
            seen_services.add(service)
            found.append({
                "service": service,
                "username": entry["username"],
                "password": entry["password"],
                "source": "browser",
            })

    return found
