"""Unit tests for agent.google_oauth — Gemini OAuth PKCE flow.

All network calls and filesystem I/O are mocked; no real HTTP requests or
file writes occur.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_creds(*, access_token="tok_access", refresh_token="tok_refresh",
                expires_at=None, email="user@example.com",
                client_id="cid", client_secret="csec"):
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at or (time.time() + 3600),
        "email": email,
        "client_id": client_id,
        "client_secret": client_secret,
        "token_type": "Bearer",
    }


# ---------------------------------------------------------------------------
# _generate_pkce_pair
# ---------------------------------------------------------------------------

class TestGeneratePkcePair:
    def test_verifier_length(self):
        from agent.google_oauth import _generate_pkce_pair
        verifier, _ = _generate_pkce_pair()
        # secrets.token_urlsafe(32) → 43 base64url chars
        assert len(verifier) >= 40

    def test_challenge_is_s256(self):
        from agent.google_oauth import _generate_pkce_pair
        verifier, challenge = _generate_pkce_pair()
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        assert challenge == expected

    def test_pair_is_unique(self):
        from agent.google_oauth import _generate_pkce_pair
        pairs = {_generate_pkce_pair()[0] for _ in range(5)}
        assert len(pairs) == 5


# ---------------------------------------------------------------------------
# _build_auth_url
# ---------------------------------------------------------------------------

class TestBuildAuthUrl:
    def test_contains_required_params(self):
        from agent.google_oauth import _build_auth_url, GOOGLE_AUTH_URL
        url = _build_auth_url("my_state", "my_challenge", "my_client_id")
        assert url.startswith(GOOGLE_AUTH_URL)
        assert "state=my_state" in url
        assert "code_challenge=my_challenge" in url
        assert "code_challenge_method=S256" in url
        assert "client_id=my_client_id" in url
        assert "response_type=code" in url
        assert "access_type=offline" in url

    def test_prompt_consent_present(self):
        from agent.google_oauth import _build_auth_url
        url = _build_auth_url("s", "c", "cid")
        assert "prompt=consent" in url


# ---------------------------------------------------------------------------
# load_credentials / save_credentials / clear_credentials
# ---------------------------------------------------------------------------

class TestCredentialIO:
    def test_load_missing_file_returns_empty(self, tmp_path):
        from agent import google_oauth
        with patch.object(google_oauth, "_creds_path", return_value=tmp_path / "missing.json"):
            result = google_oauth.load_credentials()
        assert result == {}

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        from agent import google_oauth
        bad = tmp_path / "bad.json"
        bad.write_text("not json!!!")
        with patch.object(google_oauth, "_creds_path", return_value=bad):
            result = google_oauth.load_credentials()
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        from agent import google_oauth
        path = tmp_path / "gemini_oauth.json"
        creds = _make_creds()
        with patch.object(google_oauth, "_creds_path", return_value=path):
            google_oauth.save_credentials(creds)
            loaded = google_oauth.load_credentials()
        assert loaded["access_token"] == creds["access_token"]
        assert loaded["email"] == creds["email"]

    def test_save_sets_0o600_permissions(self, tmp_path):
        from agent import google_oauth
        path = tmp_path / "gemini_oauth.json"
        with patch.object(google_oauth, "_creds_path", return_value=path):
            google_oauth.save_credentials(_make_creds())
        file_mode = oct(stat.S_IMODE(path.stat().st_mode))
        assert file_mode == oct(0o600)

    def test_clear_deletes_file(self, tmp_path):
        from agent import google_oauth
        path = tmp_path / "gemini_oauth.json"
        path.write_text("{}")
        with patch.object(google_oauth, "_creds_path", return_value=path):
            google_oauth.clear_credentials()
        assert not path.exists()

    def test_clear_missing_file_does_not_raise(self, tmp_path):
        from agent import google_oauth
        with patch.object(google_oauth, "_creds_path", return_value=tmp_path / "nope.json"):
            google_oauth.clear_credentials()  # should not raise


# ---------------------------------------------------------------------------
# _token_is_expiring
# ---------------------------------------------------------------------------

class TestTokenIsExpiring:
    def test_no_expires_at_is_expiring(self):
        from agent.google_oauth import _token_is_expiring
        assert _token_is_expiring({}) is True

    def test_future_token_not_expiring(self):
        from agent.google_oauth import _token_is_expiring
        creds = {"expires_at": time.time() + 7200}
        assert _token_is_expiring(creds) is False

    def test_expiring_within_skew(self):
        from agent.google_oauth import _token_is_expiring
        creds = {"expires_at": time.time() + 60}
        assert _token_is_expiring(creds, skew=300) is True

    def test_already_expired(self):
        from agent.google_oauth import _token_is_expiring
        creds = {"expires_at": time.time() - 1}
        assert _token_is_expiring(creds) is True


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------

class TestRefreshAccessToken:
    def _mock_response(self, status=200, json_data=None):
        resp = Mock()
        resp.status_code = status
        resp.json.return_value = json_data or {
            "access_token": "new_access",
            "expires_in": 3600,
        }
        resp.text = json.dumps(json_data or {})
        return resp

    def test_updates_access_token(self, tmp_path):
        from agent import google_oauth
        creds = _make_creds(expires_at=time.time() + 10)
        resp = self._mock_response()
        path = tmp_path / "gemini_oauth.json"
        with patch.object(google_oauth, "_creds_path", return_value=path), \
             patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = resp
            updated = google_oauth.refresh_access_token(creds)
        assert updated["access_token"] == "new_access"

    def test_raises_on_missing_refresh_token(self):
        from agent.google_oauth import refresh_access_token, GeminiOAuthError
        with pytest.raises(GeminiOAuthError, match="refresh_token"):
            refresh_access_token({"access_token": "x"})

    def test_raises_on_http_error(self):
        from agent.google_oauth import refresh_access_token, GeminiOAuthError
        creds = _make_creds()
        resp = self._mock_response(status=401)
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = resp
            with pytest.raises(GeminiOAuthError, match="401"):
                refresh_access_token(creds)

    def test_raises_on_missing_client_creds(self):
        from agent.google_oauth import refresh_access_token, GeminiOAuthError
        creds = {"refresh_token": "rtok", "client_id": "", "client_secret": ""}
        with patch.dict(os.environ, {"HERMES_GEMINI_CLIENT_ID": "", "HERMES_GEMINI_CLIENT_SECRET": ""}):
            with pytest.raises(GeminiOAuthError, match="client credentials"):
                refresh_access_token(creds)

    def test_rotated_refresh_token_saved(self, tmp_path):
        from agent import google_oauth
        creds = _make_creds()
        resp = self._mock_response(json_data={
            "access_token": "new_acc",
            "expires_in": 3600,
            "refresh_token": "rotated_refresh",
        })
        path = tmp_path / "gemini_oauth.json"
        with patch.object(google_oauth, "_creds_path", return_value=path), \
             patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = resp
            updated = google_oauth.refresh_access_token(creds)
        assert updated["refresh_token"] == "rotated_refresh"


# ---------------------------------------------------------------------------
# get_valid_access_token
# ---------------------------------------------------------------------------

class TestGetValidAccessToken:
    def test_returns_valid_token_without_refresh(self, tmp_path):
        from agent import google_oauth
        creds = _make_creds(expires_at=time.time() + 7200)
        path = tmp_path / "gemini_oauth.json"
        with patch.object(google_oauth, "_creds_path", return_value=path):
            google_oauth.save_credentials(creds)
            token = google_oauth.get_valid_access_token()
        assert token == creds["access_token"]

    def test_raises_when_no_creds(self, tmp_path):
        from agent import google_oauth
        from agent.google_oauth import GeminiOAuthError
        path = tmp_path / "missing.json"
        with patch.object(google_oauth, "_creds_path", return_value=path):
            with pytest.raises(GeminiOAuthError, match="No Gemini OAuth credentials"):
                google_oauth.get_valid_access_token()

    def test_refreshes_expiring_token(self, tmp_path):
        from agent import google_oauth
        from agent.google_oauth import GeminiOAuthError
        creds = _make_creds(expires_at=time.time() + 60)  # expiring within skew
        path = tmp_path / "gemini_oauth.json"
        new_resp = Mock()
        new_resp.status_code = 200
        new_resp.json.return_value = {"access_token": "refreshed_tok", "expires_in": 3600}
        new_resp.text = "{}"
        with patch.object(google_oauth, "_creds_path", return_value=path), \
             patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = new_resp
            google_oauth.save_credentials(creds)
            token = google_oauth.get_valid_access_token()
        assert token == "refreshed_tok"


# ---------------------------------------------------------------------------
# _exchange_code
# ---------------------------------------------------------------------------

class TestExchangeCode:
    def test_returns_tokens_on_success(self):
        from agent.google_oauth import _exchange_code
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "acc", "refresh_token": "ref", "expires_in": 3600
        }
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = resp
            result = _exchange_code("code123", "verifier", "cid", "csec")
        assert result["access_token"] == "acc"

    def test_raises_on_http_error(self):
        from agent.google_oauth import _exchange_code, GeminiOAuthError
        resp = Mock()
        resp.status_code = 400
        resp.text = "bad_request"
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = resp
            with pytest.raises(GeminiOAuthError, match="400"):
                _exchange_code("code", "ver", "cid", "csec")

    def test_raises_on_network_error(self):
        from agent.google_oauth import _exchange_code, GeminiOAuthError
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = \
                Exception("connection refused")
            with pytest.raises(GeminiOAuthError, match="Token exchange request failed"):
                _exchange_code("c", "v", "id", "sec")


# ---------------------------------------------------------------------------
# get_auth_status
# ---------------------------------------------------------------------------

class TestGetAuthStatus:
    def test_not_logged_in_when_no_file(self, tmp_path):
        from agent import google_oauth
        with patch.object(google_oauth, "_creds_path", return_value=tmp_path / "none.json"):
            status = google_oauth.get_auth_status()
        assert status["logged_in"] is False

    def test_logged_in_with_valid_creds(self, tmp_path):
        from agent import google_oauth
        path = tmp_path / "gemini_oauth.json"
        creds = _make_creds(expires_at=time.time() + 7200)
        with patch.object(google_oauth, "_creds_path", return_value=path):
            google_oauth.save_credentials(creds)
            status = google_oauth.get_auth_status()
        assert status["logged_in"] is True
        assert status["email"] == "user@example.com"
        assert status["token_expiring"] is False
        assert status["has_refresh_token"] is True

    def test_expiring_token_flagged(self, tmp_path):
        from agent import google_oauth
        path = tmp_path / "gemini_oauth.json"
        creds = _make_creds(expires_at=time.time() - 1)  # already expired
        with patch.object(google_oauth, "_creds_path", return_value=path):
            google_oauth.save_credentials(creds)
            status = google_oauth.get_auth_status()
        assert status["token_expiring"] is True


# ---------------------------------------------------------------------------
# _require_client_creds
# ---------------------------------------------------------------------------

class TestRequireClientCreds:
    def test_raises_when_both_missing(self):
        from agent.google_oauth import _require_client_creds, GeminiOAuthError
        with pytest.raises(GeminiOAuthError, match="client credentials"):
            _require_client_creds("", "")

    def test_raises_when_client_id_missing(self):
        from agent.google_oauth import _require_client_creds, GeminiOAuthError
        with pytest.raises(GeminiOAuthError):
            _require_client_creds("", "secret")

    def test_no_raise_when_both_present(self):
        from agent.google_oauth import _require_client_creds
        _require_client_creds("my_client_id", "my_secret")  # should not raise


# ---------------------------------------------------------------------------
# _is_remote_session
# ---------------------------------------------------------------------------

class TestIsRemoteSession:
    def test_false_when_no_ssh_env(self):
        from agent.google_oauth import _is_remote_session
        env = {k: v for k, v in os.environ.items()
               if k not in ("SSH_CLIENT", "SSH_TTY")}
        with patch.dict(os.environ, env, clear=True):
            assert _is_remote_session() is False

    def test_true_with_ssh_client(self):
        from agent.google_oauth import _is_remote_session
        with patch.dict(os.environ, {"SSH_CLIENT": "1.2.3.4 1234 22"}):
            assert _is_remote_session() is True

    def test_true_with_ssh_tty(self):
        from agent.google_oauth import _is_remote_session
        with patch.dict(os.environ, {"SSH_TTY": "/dev/pts/0"}):
            assert _is_remote_session() is True
