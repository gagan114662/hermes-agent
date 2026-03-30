import pytest
from unittest.mock import patch, MagicMock
from tools.credential_harvester import (
    _map_domain_to_service,
    _parse_keychain_output,
    harvest_credentials,
    SERVICE_MAP,
)

def test_map_domain_to_service_known():
    assert _map_domain_to_service("gmail.com") == "gmail"
    assert _map_domain_to_service("app.shopify.com") == "shopify"
    assert _map_domain_to_service("quickbooks.intuit.com") == "quickbooks"

def test_map_domain_to_service_unknown():
    assert _map_domain_to_service("unknownapp.xyz") is None

def test_parse_keychain_output_extracts_fields():
    raw = '''keychain: "/Users/user/Library/Keychains/login.keychain-db"
class: "inet"
attributes:
    "acct"<blob>="user@gmail.com"
    "srvr"<blob>="gmail.com"
password: "mypassword123"
'''
    result = _parse_keychain_output(raw)
    assert result["username"] == "user@gmail.com"
    assert result["domain"] == "gmail.com"
    assert result["password"] == "mypassword123"

def test_parse_keychain_output_missing_fields():
    result = _parse_keychain_output("no fields here")
    assert result is None

def test_harvest_credentials_returns_list(monkeypatch):
    mock_output = '''keychain: "/Users/user/Library/Keychains/login.keychain-db"
class: "inet"
attributes:
    "acct"<blob>="owner@shopify.com"
    "srvr"<blob>="app.shopify.com"
password: "shopify-token-abc"
'''
    monkeypatch.setattr(
        "tools.credential_harvester._run_keychain_dump",
        lambda: mock_output
    )
    monkeypatch.setattr(
        "tools.credential_harvester._read_browser_passwords",
        lambda: []
    )
    results = harvest_credentials()
    assert len(results) == 1
    assert results[0]["service"] == "shopify"
    assert results[0]["username"] == "owner@shopify.com"
    assert results[0]["password"] == "shopify-token-abc"

def test_service_map_covers_common_smb_tools():
    required = ["gmail", "shopify", "quickbooks", "stripe", "calendly", "notion", "slack"]
    for svc in required:
        assert any(svc in v for v in SERVICE_MAP.values()), f"Missing service: {svc}"
