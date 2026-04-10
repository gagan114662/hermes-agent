"""Google OAuth 2.0 + PKCE flow for Gemini API access.

Implements Authorization Code + PKCE (S256) with a localhost callback server.
Tokens are stored at ~/.hermes/gemini_oauth.json (separate from the Gemini CLI).

Usage:
    from agent.google_oauth import get_valid_access_token, start_oauth_flow

    # Interactive login (opens browser):
    creds = start_oauth_flow()

    # Get a valid (auto-refreshed) token before each API call:
    token = get_valid_access_token()

Client credentials:
    Override via env vars HERMES_GEMINI_CLIENT_ID / HERMES_GEMINI_CLIENT_SECRET.
    If unset, falls back to the built-in desktop-app credentials shipped with
    Hermes (registered on the Hermes GCP project).  Google treats installed-app
    client secrets as non-confidential.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import stat
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

OAUTH_REDIRECT_PORT = 8085
OAUTH_REDIRECT_URI = f"http://localhost:{OAUTH_REDIRECT_PORT}/oauth2callback"

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/generative-language",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# Refresh 5 minutes before expiry
TOKEN_REFRESH_SKEW_SECONDS = 300

# Built-in desktop-app credentials (non-confidential per Google's policy).
# Users can override via HERMES_GEMINI_CLIENT_ID / HERMES_GEMINI_CLIENT_SECRET.
_DEFAULT_CLIENT_ID = os.environ.get("HERMES_GEMINI_CLIENT_ID", "")
_DEFAULT_CLIENT_SECRET = os.environ.get("HERMES_GEMINI_CLIENT_SECRET", "")

CREDS_FILE_NAME = "gemini_oauth.json"

# ---------------------------------------------------------------------------
# Credential file helpers
# ---------------------------------------------------------------------------

def _creds_path() -> Path:
    """Return path to ~/.hermes/gemini_oauth.json."""
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / CREDS_FILE_NAME


def load_credentials() -> Dict[str, Any]:
    """Load stored OAuth credentials. Returns {} if file missing or corrupt."""
    path = _creds_path()
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as exc:
        logger.debug("Could not load gemini_oauth.json: %s", exc)
    return {}


def save_credentials(creds: Dict[str, Any]) -> None:
    """Atomically save credentials with 0o600 permissions."""
    path = _creds_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(creds, indent=2))
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def clear_credentials() -> None:
    """Delete stored credentials (logout)."""
    path = _creds_path()
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Token lifecycle
# ---------------------------------------------------------------------------

def _token_is_expiring(creds: Dict[str, Any], skew: int = TOKEN_REFRESH_SKEW_SECONDS) -> bool:
    """Return True if the access token expires within *skew* seconds."""
    expires_at = creds.get("expires_at")
    if not expires_at:
        return True
    return time.time() >= (float(expires_at) - skew)


def refresh_access_token(creds: Dict[str, Any]) -> Dict[str, Any]:
    """Exchange the refresh_token for a fresh access_token.

    Updates and saves the creds dict in-place, returns the updated dict.
    Raises ``GeminiOAuthError`` on failure.
    """
    refresh_token = creds.get("refresh_token", "")
    if not refresh_token:
        raise GeminiOAuthError(
            "No refresh_token stored. Re-run `hermes /model` and choose "
            "'Google Gemini (OAuth)'."
        )

    client_id = creds.get("client_id") or _DEFAULT_CLIENT_ID
    client_secret = creds.get("client_secret") or _DEFAULT_CLIENT_SECRET
    _require_client_creds(client_id, client_secret)

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except Exception as exc:
        raise GeminiOAuthError(f"Token refresh request failed: {exc}") from exc

    if resp.status_code != 200:
        body = resp.text[:300]
        raise GeminiOAuthError(
            f"Token refresh returned HTTP {resp.status_code}: {body}"
        )

    data = resp.json()
    creds["access_token"] = data["access_token"]
    creds["expires_at"] = time.time() + int(data.get("expires_in", 3600))
    # Google may rotate the refresh_token; keep the new one if present.
    if data.get("refresh_token"):
        creds["refresh_token"] = data["refresh_token"]

    save_credentials(creds)
    logger.debug("Gemini OAuth access token refreshed (expires in %ss)", data.get("expires_in"))
    return creds


def get_valid_access_token() -> str:
    """Return a valid access token, refreshing if expiring.

    Raises ``GeminiOAuthError`` if no credentials are stored or refresh fails.
    """
    creds = load_credentials()
    if not creds:
        raise GeminiOAuthError(
            "No Gemini OAuth credentials found. Run `hermes /model` and "
            "choose 'Google Gemini (OAuth)' to authenticate."
        )
    if _token_is_expiring(creds):
        creds = refresh_access_token(creds)
    token = creds.get("access_token", "")
    if not token:
        raise GeminiOAuthError("access_token missing after refresh.")
    return token


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = secrets.token_urlsafe(32)          # 32 bytes → 43-char base64url
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _build_auth_url(state: str, code_challenge: str, client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",       # ensures refresh_token is always returned
    }
    return GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


# ---------------------------------------------------------------------------
# Localhost callback server
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth callback."""

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/oauth2callback":
            self.send_response(404)
            self.end_headers()
            return

        params = dict(urllib.parse.parse_qsl(parsed.query))
        self.server._callback_params = params  # type: ignore[attr-defined]

        if "error" in params:
            body = b"<h2>Login cancelled or failed.</h2><p>You can close this tab.</p>"
        else:
            body = (
                b"<h2>Hermes: login successful!</h2>"
                b"<p>You can close this tab and return to your terminal.</p>"
            )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args, **kwargs):  # suppress server logs
        pass


def _run_callback_server(timeout: int = 120) -> Dict[str, str]:
    """Start HTTP server on OAUTH_REDIRECT_PORT, block until callback or timeout.

    Returns the query-string parameters from the callback URL.
    Raises ``GeminiOAuthError`` on timeout or missing code.
    """
    server = HTTPServer(("127.0.0.1", OAUTH_REDIRECT_PORT), _CallbackHandler)
    server._callback_params = {}  # type: ignore[attr-defined]
    server.timeout = timeout

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        server.handle_request()
        if server._callback_params:  # type: ignore[attr-defined]
            break

    server.server_close()
    params: Dict[str, str] = server._callback_params  # type: ignore[attr-defined]

    if not params:
        raise GeminiOAuthError("Login timed out waiting for browser callback.")
    if "error" in params:
        raise GeminiOAuthError(f"Google returned error: {params['error']}")
    if "code" not in params:
        raise GeminiOAuthError("Callback missing authorization code.")
    return params


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

def _exchange_code(
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
) -> Dict[str, Any]:
    """Exchange authorization code + PKCE verifier for tokens."""
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": OAUTH_REDIRECT_URI,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except Exception as exc:
        raise GeminiOAuthError(f"Token exchange request failed: {exc}") from exc

    if resp.status_code != 200:
        body = resp.text[:300]
        raise GeminiOAuthError(
            f"Token exchange returned HTTP {resp.status_code}: {body}"
        )

    return resp.json()


def _fetch_user_email(access_token: str) -> str:
    """Return the Google account email, or '' on failure."""
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code == 200:
                return r.json().get("email", "")
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_oauth_flow(
    *,
    client_id: str = "",
    client_secret: str = "",
    open_browser: bool = True,
    callback_timeout: int = 120,
) -> Dict[str, Any]:
    """Run the full PKCE Authorization Code flow and persist credentials.

    Opens the browser, starts a localhost callback server, exchanges the code
    for tokens, fetches the user's email, saves to ~/.hermes/gemini_oauth.json,
    and returns the credentials dict.

    Args:
        client_id: Override OAuth client ID (defaults to HERMES_GEMINI_CLIENT_ID
                   env var or the built-in Hermes credentials).
        client_secret: Override OAuth client secret.
        open_browser: If False, just print the URL (for headless/SSH use).
        callback_timeout: Seconds to wait for the browser callback.

    Raises:
        GeminiOAuthError: on any step failure.
    """
    client_id = client_id or _DEFAULT_CLIENT_ID
    client_secret = client_secret or _DEFAULT_CLIENT_SECRET
    _require_client_creds(client_id, client_secret)

    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = _generate_pkce_pair()
    auth_url = _build_auth_url(state, code_challenge, client_id)

    print()
    if open_browser and not _is_remote_session():
        print("Opening your browser for Google sign-in...")
        print(f"  URL: {auth_url}")
        webbrowser.open(auth_url)
    else:
        print("Open this URL in your browser to sign in with Google:")
        print(f"\n  {auth_url}\n")

    print(f"\nWaiting for browser callback on port {OAUTH_REDIRECT_PORT}...")
    print("(Press Ctrl+C to cancel)\n")

    try:
        params = _run_callback_server(timeout=callback_timeout)
    except KeyboardInterrupt:
        print("\nLogin cancelled.")
        raise SystemExit(130)

    # Validate state to prevent CSRF
    if params.get("state") != state:
        raise GeminiOAuthError("State mismatch — possible CSRF attack. Aborting.")

    code = params["code"]
    tokens = _exchange_code(code, code_verifier, client_id, client_secret)

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in = int(tokens.get("expires_in", 3600))

    email = _fetch_user_email(access_token)

    creds: Dict[str, Any] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in,
        "email": email,
        "token_type": tokens.get("token_type", "Bearer"),
    }
    save_credentials(creds)

    return creds


# ---------------------------------------------------------------------------
# Auth status
# ---------------------------------------------------------------------------

def get_auth_status() -> Dict[str, Any]:
    """Return a dict describing current auth state (for display/diagnostics)."""
    creds = load_credentials()
    if not creds:
        return {"logged_in": False}

    expiring = _token_is_expiring(creds, skew=0)
    return {
        "logged_in": True,
        "email": creds.get("email", ""),
        "expires_at": creds.get("expires_at"),
        "token_expiring": expiring,
        "has_refresh_token": bool(creds.get("refresh_token")),
        "creds_file": str(_creds_path()),
    }


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class GeminiOAuthError(Exception):
    """Raised when any step of the Gemini OAuth flow fails."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _require_client_creds(client_id: str, client_secret: str) -> None:
    if not client_id or not client_secret:
        raise GeminiOAuthError(
            "Gemini OAuth client credentials not configured.\n"
            "Set HERMES_GEMINI_CLIENT_ID and HERMES_GEMINI_CLIENT_SECRET env vars\n"
            "or register a Desktop OAuth app at https://console.cloud.google.com/\n"
            "and enable the 'Generative Language API'."
        )


def _is_remote_session() -> bool:
    """True if running over SSH (webbrowser.open won't work on the local screen)."""
    return bool(os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"))
