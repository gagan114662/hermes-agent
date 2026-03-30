"""
Credential Harvester — detects services the owner uses via macOS Keychain.

Queries each known service domain individually using `security find-internet-password`.
Each query triggers a macOS system dialog the first time ("Always Allow" = never asked again).
No bulk dumps. No silent access. Credentials used immediately to configure MCP, then discarded.
"""
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Ordered by priority — most common SMB tools first
KNOWN_SERVICES = [
    # (domain, service_name, display_name)
    ("mail.google.com",         "gmail",        "Gmail"),
    ("accounts.google.com",     "google",       "Google"),
    ("app.shopify.com",         "shopify",      "Shopify"),
    ("quickbooks.intuit.com",   "quickbooks",   "QuickBooks"),
    ("dashboard.stripe.com",    "stripe",       "Stripe"),
    ("app.hubspot.com",         "hubspot",      "HubSpot"),
    ("calendly.com",            "calendly",     "Calendly"),
    ("notion.so",               "notion",       "Notion"),
    ("slack.com",               "slack",        "Slack"),
    ("airtable.com",            "airtable",     "Airtable"),
    ("squareup.com",            "square",       "Square"),
    ("xero.com",                "xero",         "Xero"),
    ("app.woocommerce.com",     "woocommerce",  "WooCommerce"),
    ("trello.com",              "trello",       "Trello"),
    ("github.com",              "github",       "GitHub"),
    ("business.google.com",     "google_business", "Google Business Profile"),
    ("ads.google.com",          "google_ads",   "Google Ads"),
    ("business.facebook.com",   "meta",         "Meta Business"),
    ("mailchimp.com",           "mailchimp",    "Mailchimp"),
    ("wordpress.com",           "wordpress",    "WordPress"),
]


def _query_keychain(domain: str) -> Optional[str]:
    """
    Query macOS Keychain for a specific domain.
    First call: triggers macOS system dialog asking user permission.
    After "Always Allow": silent forever.
    Returns password string or None if not found / denied.
    """
    try:
        result = subprocess.run(
            ["security", "find-internet-password", "-s", domain, "-w"],
            capture_output=True,
            text=True,
            timeout=30,  # user has 30s to respond to dialog
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except subprocess.TimeoutExpired:
        logger.debug("Keychain dialog timed out for %s", domain)
        return None
    except Exception as e:
        logger.debug("Keychain query failed for %s: %s", domain, e)
        return None


def _query_keychain_username(domain: str) -> Optional[str]:
    """Get the username/account stored for a domain (no dialog needed)."""
    try:
        result = subprocess.run(
            ["security", "find-internet-password", "-s", domain],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if '"acct"' in line and '<blob>' in line:
                    # Extract: "acct"<blob>="user@example.com"
                    import re
                    m = re.search(r'"acct"<blob>="([^"]+)"', line)
                    if m:
                        return m.group(1)
        return None
    except Exception:
        return None


def harvest_credentials() -> list:
    """
    Probe each known service. For each one found in Keychain:
    - Triggers macOS system dialog on first run
    - Silent on subsequent runs (after user clicks Always Allow)
    Returns list of {service, display_name, username, password, source} dicts.
    """
    found = []
    for domain, service, display_name in KNOWN_SERVICES:
        password = _query_keychain(domain)
        if password:
            username = _query_keychain_username(domain) or ""
            found.append({
                "service": service,
                "display_name": display_name,
                "domain": domain,
                "username": username,
                "password": password,
                "source": "keychain",
            })
            logger.info("Found credentials for %s (%s)", display_name, username)
    return found


def detect_services_only() -> list:
    """
    Detect which services the owner has accounts for WITHOUT accessing passwords.
    Uses `security find-internet-password -s <domain>` (no -w flag = no password, no dialog).
    Returns list of {service, display_name, domain, username} dicts.
    Use this for the "I found these tools" detection screen before asking permission.
    """
    found = []
    import re
    for domain, service, display_name in KNOWN_SERVICES:
        try:
            result = subprocess.run(
                ["security", "find-internet-password", "-s", domain],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                username = ""
                for line in result.stdout.splitlines():
                    m = re.search(r'"acct"<blob>="([^"]+)"', line)
                    if m:
                        username = m.group(1)
                        break
                found.append({
                    "service": service,
                    "display_name": display_name,
                    "domain": domain,
                    "username": username,
                })
        except Exception:
            continue
    return found
