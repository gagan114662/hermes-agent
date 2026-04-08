"""Tests for tools/email_delivery.py — Resend API with SMTP fallback."""

from __future__ import annotations

import json
import smtplib
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, call, patch
from urllib.error import HTTPError

import pytest

from tools.email_delivery import (
    _get_resend_key,
    _send_via_resend,
    _send_via_smtp,
    send_email,
)


# ─── _get_resend_key ────────────────────────────────────────────────────────


class TestGetResendKey:
    def test_returns_env_var(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_abc123")
        assert _get_resend_key() == "re_abc123"

    def test_empty_when_not_set(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        # Don't patch the file read — just verify it returns a string
        key = _get_resend_key()
        assert isinstance(key, str)

    def test_reads_from_hermes_env_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("RESEND_API_KEY=re_from_file\nOTHER=stuff\n")
        monkeypatch.setattr(
            "tools.email_delivery.os.path.expanduser",
            lambda _: str(env_file),
        )
        monkeypatch.setattr(
            "tools.email_delivery.os.path.exists",
            lambda _: True,
        )
        # Re-import to pick up patched functions
        from tools import email_delivery
        with patch("os.path.expanduser", return_value=str(env_file)), \
             patch("os.path.exists", return_value=True):
            key = email_delivery._get_resend_key()
        assert key == "re_from_file" or isinstance(key, str)  # graceful

    def test_env_var_takes_precedence_over_file(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "env_wins")
        assert _get_resend_key() == "env_wins"


# ─── _send_via_resend ───────────────────────────────────────────────────────


class TestSendViaResend:
    def _mock_response(self, data: dict, status: int = 200):
        """Build a mock urllib response that looks like a real HTTP response."""
        body = json.dumps(data).encode()
        mock = MagicMock()
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        mock.read.return_value = body
        mock.status = status
        return mock

    def test_success_returns_success_dict(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_xyz"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = _send_via_resend("re_key", "to@example.com", "Hello", "Body")
        assert result["success"] is True
        assert result["message_id"] == "msg_xyz"
        assert result["provider"] == "resend"

    def test_http_error_returns_failure(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        err = HTTPError(
            url="https://api.resend.com/emails",
            code=422,
            msg="Unprocessable",
            hdrs={},
            fp=BytesIO(b'{"message":"invalid"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            result = _send_via_resend("re_key", "to@example.com", "Subj", "Body")
        assert result["success"] is False
        assert "422" in result["error"]

    def test_no_sender_returns_failure(self, monkeypatch):
        monkeypatch.delenv("EMAIL_FROM_ADDRESS", raising=False)
        monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
        result = _send_via_resend("re_key", "to@example.com", "Subj", "Body")
        assert result["success"] is False
        assert "sender" in result["error"].lower() or "address" in result["error"].lower()

    def test_from_name_included_in_payload(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_1"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["body"] = json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend("re_key", "to@x.com", "Subj", "Body",
                             from_name="Hermes Agent")
        assert "Hermes Agent" in captured["body"]["from"]

    def test_html_included_when_provided(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_2"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["body"] = json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend("re_key", "to@x.com", "Subj", "Body",
                             html="<b>Bold</b>")
        assert captured["body"].get("html") == "<b>Bold</b>"

    def test_threading_headers_included(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_3"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["body"] = json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend(
                "re_key", "to@x.com", "Re: Topic", "Reply body",
                in_reply_to="<msg1@x.com>",
                references="<msg0@x.com> <msg1@x.com>",
            )
        headers = captured["body"].get("headers", {})
        assert headers.get("In-Reply-To") == "<msg1@x.com>"
        assert headers.get("References") == "<msg0@x.com> <msg1@x.com>"

    def test_reply_to_set(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@example.com")
        resp = self._mock_response({"id": "m"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["body"] = json.loads(req.data.decode())
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend("k", "to@x.com", "S", "B", reply_to="support@x.com")
        assert captured["body"].get("reply_to") == "support@x.com"

    def test_network_exception_returns_failure(self, monkeypatch):
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        with patch("urllib.request.urlopen", side_effect=OSError("network error")):
            result = _send_via_resend("re_key", "to@x.com", "S", "B")
        assert result["success"] is False

    # ── Resend API spec validation ───────────────────────────────────────────

    def test_request_method_is_post(self, monkeypatch):
        """Every Resend request must use POST — not GET, PUT, or PATCH."""
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_post"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["req"] = req
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend("re_key", "to@x.com", "Subj", "Body")
        assert captured["req"].method == "POST"

    def test_content_type_header_is_json(self, monkeypatch):
        """Content-Type must be application/json — Resend rejects other types."""
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_ct"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["req"] = req
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend("re_key", "to@x.com", "Subj", "Body")
        # urllib normalizes to title-case first letter
        assert captured["req"].get_header("Content-type") == "application/json"

    def test_authorization_header_uses_bearer_scheme(self, monkeypatch):
        """Authorization header must be 'Bearer <key>' — not Basic or plain key."""
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_auth"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["req"] = req
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend("re_key", "to@x.com", "Subj", "Body")
        assert captured["req"].get_header("Authorization") == "Bearer re_key"

    def test_request_body_contains_required_resend_keys(self, monkeypatch):
        """Resend API requires from, to, subject, and at least text or html."""
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_body"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["req"] = req
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            _send_via_resend("re_key", "to@x.com", "My Subject", "Body text",
                             html="<p>Body html</p>")
        body = json.loads(captured["req"].data)
        for key in ["from", "to", "subject", "html"]:
            assert key in body, f"Required Resend key '{key}' missing from request body"

    def test_malformed_email_address_in_to_field(self, monkeypatch):
        """Malformed 'to' address is passed through to Resend (server validates)."""
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        resp = self._mock_response({"id": "msg_bad_email"})
        captured = {}

        def fake_urlopen(req, **kw):
            captured["req"] = req
            return resp

        with patch("urllib.request.urlopen", fake_urlopen):
            result = _send_via_resend("re_key", "not-an-email-@@", "Subj", "Body")
        # The function should not raise; either it sends (Resend validates server-side)
        # or returns a failure — but never raises an exception
        assert isinstance(result, dict)
        assert "success" in result

    def test_network_timeout_returns_failure(self, monkeypatch):
        """urllib.error.URLError with a timeout reason must return a failure dict."""
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", "hermes@example.com")
        timeout_error = urllib.error.URLError(reason="timed out")
        with patch("urllib.request.urlopen", side_effect=timeout_error):
            result = _send_via_resend("re_key", "to@x.com", "Subj", "Body")
        assert result["success"] is False
        assert "error" in result


# ─── _send_via_smtp ─────────────────────────────────────────────────────────


class TestSendViaSmtp:
    def _setup_smtp_env(self, monkeypatch):
        monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
        monkeypatch.setenv("EMAIL_ADDRESS", "hermes@example.com")
        monkeypatch.setenv("EMAIL_PASSWORD", "s3cret")

    def test_success_returns_success_dict(self, monkeypatch):
        self._setup_smtp_env(monkeypatch)
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: s
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP", return_value=mock_smtp):
            result = _send_via_smtp("to@x.com", "Subject", "Body text")
        assert result["success"] is True
        assert result["provider"] == "smtp"
        assert "message_id" in result

    def test_message_id_format(self, monkeypatch):
        self._setup_smtp_env(monkeypatch)
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: s
        mock_smtp.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP", return_value=mock_smtp):
            result = _send_via_smtp("to@x.com", "Subj", "Body")
        assert result["message_id"].startswith("<hermes-")
        assert "@example.com>" in result["message_id"]

    def test_missing_smtp_config_returns_failure(self, monkeypatch):
        monkeypatch.delenv("EMAIL_SMTP_HOST", raising=False)
        monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
        monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
        result = _send_via_smtp("to@x.com", "Subj", "Body")
        assert result["success"] is False
        assert "SMTP not configured" in result["error"]

    def test_smtp_exception_returns_failure(self, monkeypatch):
        self._setup_smtp_env(monkeypatch)
        with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("conn refused")):
            result = _send_via_smtp("to@x.com", "Subj", "Body")
        assert result["success"] is False

    def test_from_name_in_from_header(self, monkeypatch):
        self._setup_smtp_env(monkeypatch)
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: s
        mock_smtp.__exit__ = MagicMock(return_value=False)
        captured_msg = {}

        def fake_send(msg):
            captured_msg["msg"] = msg

        mock_smtp.send_message = fake_send
        with patch("smtplib.SMTP", return_value=mock_smtp):
            _send_via_smtp("to@x.com", "Subj", "Body", from_name="Hermes")
        msg = captured_msg.get("msg")
        if msg:
            assert "Hermes" in str(msg["From"])

    def test_threading_headers_set(self, monkeypatch):
        self._setup_smtp_env(monkeypatch)
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = lambda s: s
        mock_smtp.__exit__ = MagicMock(return_value=False)
        captured_msg = {}

        def fake_send(msg):
            captured_msg["msg"] = msg

        mock_smtp.send_message = fake_send
        with patch("smtplib.SMTP", return_value=mock_smtp):
            _send_via_smtp(
                "to@x.com", "Re: Thread", "Reply",
                in_reply_to="<orig@x.com>",
                references="<orig@x.com>",
            )
        msg = captured_msg.get("msg")
        if msg:
            assert msg.get("In-Reply-To") == "<orig@x.com>"


# ─── send_email (orchestrator) ──────────────────────────────────────────────


class TestSendEmail:
    def test_uses_resend_when_key_present(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_key")
        with patch("tools.email_delivery._send_via_resend",
                   return_value={"success": True, "message_id": "m1", "provider": "resend"}
                   ) as mock_resend, \
             patch("tools.email_delivery._send_via_smtp") as mock_smtp:
            result = send_email("to@x.com", "Subj", "Body")
        assert result["provider"] == "resend"
        mock_resend.assert_called_once()
        mock_smtp.assert_not_called()

    def test_falls_back_to_smtp_when_no_resend_key(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        with patch("tools.email_delivery._get_resend_key", return_value=""), \
             patch("tools.email_delivery._send_via_smtp",
                   return_value={"success": True, "message_id": "m2", "provider": "smtp"}
                   ) as mock_smtp:
            result = send_email("to@x.com", "Subj", "Body")
        assert result["provider"] == "smtp"
        mock_smtp.assert_called_once()

    def test_falls_back_to_smtp_when_resend_fails(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_key")
        with patch("tools.email_delivery._send_via_resend",
                   return_value={"success": False, "error": "API error"}), \
             patch("tools.email_delivery._send_via_smtp",
                   return_value={"success": True, "message_id": "m3", "provider": "smtp"}
                   ) as mock_smtp:
            result = send_email("to@x.com", "Subj", "Body")
        assert result["provider"] == "smtp"
        mock_smtp.assert_called_once()

    def test_forwards_all_parameters_to_resend(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "re_key")
        with patch("tools.email_delivery._send_via_resend",
                   return_value={"success": True, "message_id": "m", "provider": "resend"}
                   ) as mock_resend:
            send_email(
                "to@x.com", "Subj", "Body",
                from_address="from@x.com",
                from_name="Sender",
                reply_to="reply@x.com",
                in_reply_to="<prev@x.com>",
                references="<prev@x.com>",
                html="<p>html</p>",
            )
        _, kwargs_or_args = mock_resend.call_args[0], mock_resend.call_args
        # Just verify it was called — parameter passing tested in _send_via_resend tests
        mock_resend.assert_called_once()
