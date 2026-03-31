# tests/test_credential_harvester.py
import pytest
from unittest.mock import patch, MagicMock
from tools.credential_harvester import (
    KNOWN_SERVICES,
    _query_keychain,
    _query_keychain_username,
    harvest_credentials,
    detect_services_only,
)


def test_known_services_covers_smb_essentials():
    service_names = [s for _, s, _ in KNOWN_SERVICES]
    required = ["gmail", "shopify", "quickbooks", "stripe", "slack", "notion", "calendly"]
    for svc in required:
        assert svc in service_names, f"Missing service: {svc}"


def test_known_services_has_display_names():
    for domain, service, display_name in KNOWN_SERVICES:
        assert domain, "domain must not be empty"
        assert service, "service must not be empty"
        assert display_name, "display_name must not be empty"


def test_query_keychain_returns_password_on_success(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "mypassword123\n"
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
    result = _query_keychain("gmail.com")
    assert result == "mypassword123"


def test_query_keychain_returns_none_on_failure(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 44  # not found
    mock_result.stdout = ""
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
    result = _query_keychain("notfound.example.com")
    assert result is None


def test_harvest_credentials_returns_matching_services(monkeypatch):
    def mock_query_keychain(domain):
        if domain == "app.shopify.com":
            return "shopify-token-xyz"
        return None

    def mock_query_username(domain):
        if domain == "app.shopify.com":
            return "owner@mybusiness.com"
        return None

    monkeypatch.setattr("tools.credential_harvester._query_keychain", mock_query_keychain)
    monkeypatch.setattr("tools.credential_harvester._query_keychain_username", mock_query_username)

    results = harvest_credentials()
    assert len(results) == 1
    assert results[0]["service"] == "shopify"
    assert results[0]["username"] == "owner@mybusiness.com"
    assert results[0]["password"] == "shopify-token-xyz"
    assert results[0]["source"] == "keychain"


def test_detect_services_only_no_password_in_result(monkeypatch):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '    "acct"<blob>="user@gmail.com"\n'
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

    results = detect_services_only()
    for r in results:
        assert "password" not in r, "detect_services_only must not return passwords"


def test_harvest_credentials_empty_when_nothing_found(monkeypatch):
    monkeypatch.setattr("tools.credential_harvester._query_keychain", lambda d: None)
    results = harvest_credentials()
    assert results == []
