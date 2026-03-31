"""Social Media Tool — direct posting + Buffer scheduling for social media.

Capabilities:
- **Buffer** – List profiles, create/schedule posts, view queue, analytics
- **Twitter/X Direct** – Post tweets via Twitter API v2 (OAuth 1.0a)
- **LinkedIn Direct** – Publish posts via LinkedIn Marketing API
- **Smart Auto-Post** – Routes to best available method automatically
- **Content Writer** – Generate platform-tailored post ideas (zero API keys needed)

Env vars (read from ~/.hermes/.env first, then os.environ):
  BUFFER_API_TOKEN          – Buffer scheduling
  TWITTER_API_KEY           – Twitter OAuth consumer key
  TWITTER_API_SECRET        – Twitter OAuth consumer secret
  TWITTER_ACCESS_TOKEN      – Twitter user access token
  TWITTER_ACCESS_SECRET     – Twitter user access token secret
  TWITTER_BEARER_TOKEN      – Twitter read-only bearer (optional)
  LINKEDIN_ACCESS_TOKEN     – LinkedIn posting
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import random
import string
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from tools.registry import registry

logger = logging.getLogger(__name__)

_BUFFER_API = "https://api.bufferapp.com/1"
_RATE_LIMIT_MAX_RETRIES = 2
_RATE_LIMIT_BACKOFF_SECS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_token() -> str:
    """Read the Buffer API token from environment (loaded from ~/.hermes/.env at startup)."""
    return os.getenv("BUFFER_API_TOKEN", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _check_token() -> Optional[str]:
    """Return an error string if the token is missing, else None."""
    if not _get_token():
        return (
            "Error: BUFFER_API_TOKEN is not set. "
            "Get a token at https://publish.buffer.com/profile/preferences/apps "
            "and add it to ~/.hermes/.env: BUFFER_API_TOKEN=your_token"
        )
    return None


def _handle_response(resp: requests.Response) -> dict:
    """Handle a Buffer API response, including rate-limit errors."""
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", _RATE_LIMIT_BACKOFF_SECS))
        raise RateLimitError(
            f"Buffer API rate limit exceeded (60 req/min). Retry after {retry_after}s.",
            retry_after=retry_after,
        )
    resp.raise_for_status()
    return resp.json()


class RateLimitError(Exception):
    """Raised when the Buffer API returns HTTP 429."""

    def __init__(self, message: str, retry_after: int = 5):
        super().__init__(message)
        self.retry_after = retry_after


def _buf_get(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to Buffer API with rate-limit retry."""
    for attempt in range(_RATE_LIMIT_MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{_BUFFER_API}{endpoint}",
                headers=_headers(),
                params=params or {},
                timeout=30,
            )
            return _handle_response(resp)
        except RateLimitError as e:
            if attempt < _RATE_LIMIT_MAX_RETRIES:
                logger.warning("Rate limited, retrying in %ds...", e.retry_after)
                time.sleep(e.retry_after)
            else:
                raise
    return {}  # unreachable, but satisfies type checker


def _buf_post(endpoint: str, data: dict) -> dict:
    """Make a POST request to Buffer API with rate-limit retry."""
    for attempt in range(_RATE_LIMIT_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                f"{_BUFFER_API}{endpoint}",
                headers=_headers(),
                data=data,
                timeout=30,
            )
            return _handle_response(resp)
        except RateLimitError as e:
            if attempt < _RATE_LIMIT_MAX_RETRIES:
                logger.warning("Rate limited, retrying in %ds...", e.retry_after)
                time.sleep(e.retry_after)
            else:
                raise
    return {}  # unreachable


def _format_timestamp(unix_ts) -> str:
    """Convert a Unix timestamp to a human-readable string."""
    if not unix_ts:
        return "unscheduled"
    try:
        dt = datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError, OSError):
        return str(unix_ts)


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def social_profiles_fn() -> str:
    """List all connected Buffer social media profiles."""
    err = _check_token()
    if err:
        return err

    try:
        profiles = _buf_get("/profiles.json")
    except RateLimitError as e:
        return f"Rate limit: {e}"
    except requests.RequestException as e:
        return f"Error fetching profiles from Buffer: {e}"

    if not profiles:
        return "No social profiles connected to Buffer. Connect accounts at https://publish.buffer.com"

    lines = ["Connected social profiles:\n"]
    for p in profiles:
        service = p.get("service", "unknown")
        name = p.get("formatted_username") or p.get("service_username", "N/A")
        pid = p.get("id", "")
        followers = p.get("counts", {}).get("followers", "?")
        formatted_name = p.get("formatted_service", service.title())
        lines.append(
            f"  [{pid}] {formatted_name} ({service}): @{name} — {followers} followers"
        )

    return "\n".join(lines)


def social_post_fn(
    text: str,
    profile_ids: Optional[List[str]] = None,
    platform: Optional[str] = None,
    scheduled_at: Optional[str] = None,
    media_url: Optional[str] = None,
) -> str:
    """Create or schedule a social media post via Buffer."""
    err = _check_token()
    if err:
        return err

    # Resolve profile IDs
    if not profile_ids:
        if not platform:
            return (
                "Error: provide either profile_ids or platform. "
                "Use social_profiles to list available profiles."
            )
        # Find profiles matching the platform
        try:
            profiles = _buf_get("/profiles.json")
        except RateLimitError as e:
            return f"Rate limit: {e}"
        except requests.RequestException as e:
            return f"Error fetching profiles: {e}"

        matched = [
            p["id"]
            for p in profiles
            if p.get("service", "").lower() == platform.lower()
        ]
        if not matched:
            available = ", ".join(sorted({p.get("service", "") for p in profiles}))
            return f"No Buffer profile found for platform '{platform}'. Available: {available}"
        profile_ids = matched

    # Build the post payload
    payload = {"text": text, "profile_ids[]": profile_ids}

    if scheduled_at:
        # Buffer accepts Unix timestamps for scheduled_at
        # Try to parse ISO 8601 and convert, or pass through if already numeric
        try:
            ts = int(scheduled_at)
        except ValueError:
            try:
                dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
                ts = int(dt.timestamp())
            except (ValueError, TypeError):
                return f"Error: could not parse scheduled_at '{scheduled_at}'. Use ISO 8601 (e.g. '2025-01-15T14:00:00Z') or Unix timestamp."
        payload["scheduled_at"] = str(ts)
        payload["now"] = "false"

    if media_url:
        payload["media[photo]"] = media_url
        payload["media[link]"] = media_url

    try:
        result = _buf_post("/updates/create.json", payload)
    except RateLimitError as e:
        return f"Rate limit: {e}"
    except requests.RequestException as e:
        return f"Error creating post: {e}"

    if not result.get("success", True):
        return f"Buffer rejected the post: {result.get('message', 'unknown error')}"

    update = result.get("updates", [{}])
    if isinstance(update, list) and update:
        update = update[0]

    status = update.get("status", "queued")
    due_at = _format_timestamp(update.get("due_at"))
    uid = update.get("id", "")

    text_preview = text[:80] + ("..." if len(text) > 80 else "")
    if scheduled_at:
        return f"Post scheduled (id: {uid}, due: {due_at}): \"{text_preview}\""
    else:
        return f"Post added to queue (id: {uid}, status: {status}): \"{text_preview}\""


def social_queue_fn(profile_id: Optional[str] = None) -> str:
    """List pending/scheduled posts in Buffer queue."""
    err = _check_token()
    if err:
        return err

    # If no profile_id, get all profiles and show queues
    if not profile_id:
        try:
            profiles = _buf_get("/profiles.json")
        except RateLimitError as e:
            return f"Rate limit: {e}"
        except requests.RequestException as e:
            return f"Error fetching profiles: {e}"

        if not profiles:
            return "No profiles connected to Buffer."

        all_lines = []
        for p in profiles:
            pid = p["id"]
            service = p.get("service", "unknown")
            name = p.get("formatted_username") or p.get("service_username", "N/A")
            try:
                pending = _buf_get(f"/profiles/{pid}/updates/pending.json")
            except (RateLimitError, requests.RequestException):
                all_lines.append(
                    f"\n--- {service}: @{name} ---\n  (error fetching queue)"
                )
                continue

            updates = pending.get("updates", [])
            if not updates:
                all_lines.append(f"\n--- {service}: @{name} ---\n  (queue empty)")
                continue

            all_lines.append(
                f"\n--- {service}: @{name} ({len(updates)} pending) ---"
            )
            for u in updates[:10]:
                text_preview = (u.get("text") or "")[:60]
                due = _format_timestamp(u.get("due_at"))
                uid = u.get("id", "?")
                all_lines.append(f"  [{uid}] {due} | {text_preview}")

        return "\n".join(all_lines) if all_lines else "No pending posts."

    # Single profile
    try:
        pending = _buf_get(f"/profiles/{profile_id}/updates/pending.json")
    except RateLimitError as e:
        return f"Rate limit: {e}"
    except requests.RequestException as e:
        return f"Error fetching queue: {e}"

    updates = pending.get("updates", [])
    if not updates:
        return "No pending posts for this profile."

    lines = []
    for u in updates[:20]:
        text_preview = (u.get("text") or "")[:60]
        due = _format_timestamp(u.get("due_at"))
        uid = u.get("id", "?")
        lines.append(f"  [{uid}] {due} | {text_preview}")

    return f"{len(updates)} pending posts:\n" + "\n".join(lines)


def social_analytics_fn(profile_id: str) -> str:
    """Get recent sent posts with engagement stats for a Buffer profile."""
    err = _check_token()
    if err:
        return err

    if not profile_id:
        return "Error: profile_id is required. Use social_profiles to find your profile IDs."

    # Get profile info for context
    try:
        profiles = _buf_get("/profiles.json")
    except (RateLimitError, requests.RequestException):
        profiles = []

    profile_info = ""
    for p in profiles:
        if p.get("id") == profile_id:
            service = p.get("service", "unknown")
            name = p.get("formatted_username") or p.get("service_username", "N/A")
            followers = p.get("counts", {}).get("followers", "?")
            profile_info = f"{service}: @{name} ({followers} followers)"
            break

    # Fetch sent posts with engagement stats
    try:
        sent_data = _buf_get(f"/profiles/{profile_id}/updates/sent.json")
    except RateLimitError as e:
        return f"Rate limit: {e}"
    except requests.RequestException as e:
        return f"Error fetching sent posts: {e}"

    updates = sent_data.get("updates", [])
    if not updates:
        header = f"Analytics for {profile_info}\n" if profile_info else ""
        return f"{header}No sent posts found for this profile."

    lines = []
    if profile_info:
        lines.append(f"Analytics for {profile_info}")
        lines.append("=" * 50)

    total_likes = 0
    total_comments = 0
    total_shares = 0
    total_clicks = 0

    for u in updates[:25]:
        text_preview = (u.get("text") or "")[:70]
        uid = u.get("id", "?")
        sent_at = _format_timestamp(u.get("sent_at"))

        # Buffer stores engagement in statistics.* fields
        stats = u.get("statistics", {})
        likes = stats.get("likes", 0) or stats.get("favorites", 0) or 0
        comments = stats.get("comments", 0) or stats.get("replies", 0) or 0
        shares = stats.get("shares", 0) or stats.get("retweets", 0) or stats.get("repins", 0) or 0
        clicks = stats.get("clicks", 0) or 0
        reach = stats.get("reach", 0) or stats.get("impressions", 0) or 0

        total_likes += likes
        total_comments += comments
        total_shares += shares
        total_clicks += clicks

        engagement_parts = []
        if likes:
            engagement_parts.append(f"{likes} likes")
        if comments:
            engagement_parts.append(f"{comments} comments")
        if shares:
            engagement_parts.append(f"{shares} shares")
        if clicks:
            engagement_parts.append(f"{clicks} clicks")
        if reach:
            engagement_parts.append(f"{reach} reach")

        engagement_str = ", ".join(engagement_parts) if engagement_parts else "no engagement data"

        lines.append(f"\n  [{uid}] {sent_at}")
        lines.append(f"  \"{text_preview}{'...' if len(u.get('text', '')) > 70 else ''}\"")
        lines.append(f"  Engagement: {engagement_str}")

    # Summary
    lines.append("\n" + "-" * 50)
    lines.append(
        f"Totals across {min(len(updates), 25)} posts: "
        f"{total_likes} likes, {total_comments} comments, "
        f"{total_shares} shares, {total_clicks} clicks"
    )
    if len(updates) > 25:
        lines.append(f"  (showing 25 of {len(updates)} sent posts)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Env-file helper (reads ~/.hermes/.env → os.environ fallback)
# ---------------------------------------------------------------------------


def _get_env(key: str) -> str:
    """Read from ~/.hermes/.env first, then os.environ."""
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return os.environ.get(key, "")


# ---------------------------------------------------------------------------
# Twitter/X Direct Posting (API v2, OAuth 1.0a)
# ---------------------------------------------------------------------------

_TWITTER_V2_TWEET_URL = "https://api.twitter.com/2/tweets"
_TWITTER_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"


def _twitter_keys_present() -> bool:
    return all(
        _get_env(k)
        for k in (
            "TWITTER_API_KEY",
            "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN",
            "TWITTER_ACCESS_SECRET",
        )
    )


def _twitter_oauth1_header(method: str, url: str, body_params: Optional[Dict] = None) -> str:
    """Build an OAuth 1.0a Authorization header using stdlib only.

    Uses requests_oauthlib if available; falls back to manual HMAC-SHA1.
    """
    consumer_key = _get_env("TWITTER_API_KEY")
    consumer_secret = _get_env("TWITTER_API_SECRET")
    token = _get_env("TWITTER_ACCESS_TOKEN")
    token_secret = _get_env("TWITTER_ACCESS_SECRET")

    # --- try requests_oauthlib shortcut ---
    try:
        from requests_oauthlib import OAuth1
        return OAuth1(consumer_key, consumer_secret, token, token_secret)
    except ImportError:
        pass

    # --- manual OAuth 1.0a HMAC-SHA1 ---
    nonce = "".join(random.choices(string.ascii_letters + string.digits, k=32))
    timestamp = str(int(time.time()))

    oauth_params: Dict[str, str] = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_token": token,
        "oauth_version": "1.0",
    }

    # Combine oauth params + body params for signature base
    all_params = dict(oauth_params)
    if body_params:
        all_params.update(body_params)

    # Parameter string (sorted, percent-encoded)
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )

    base_string = "&".join(
        urllib.parse.quote(part, safe="")
        for part in (method.upper(), url, sorted_params)
    )

    signing_key = (
        urllib.parse.quote(consumer_secret, safe="")
        + "&"
        + urllib.parse.quote(token_secret, safe="")
    )

    signature = base64.b64encode(
        hmac.new(
            signing_key.encode(), base_string.encode(), hashlib.sha1
        ).digest()
    ).decode()

    oauth_params["oauth_signature"] = signature

    header_str = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return header_str


def twitter_post_fn(text: str, media_url: Optional[str] = None) -> str:
    """Post a tweet directly to Twitter/X via API v2."""
    if not _twitter_keys_present():
        return (
            "Error: Twitter API keys not configured.\n"
            "Add these to ~/.hermes/.env:\n"
            "  TWITTER_API_KEY=<consumer key>\n"
            "  TWITTER_API_SECRET=<consumer secret>\n"
            "  TWITTER_ACCESS_TOKEN=<access token>\n"
            "  TWITTER_ACCESS_SECRET=<access token secret>\n"
            "Get credentials at https://developer.twitter.com/en/portal/projects-and-apps"
        )

    payload: Dict[str, Any] = {"text": text}

    # If media_url provided, upload it first via v1.1 media/upload
    if media_url:
        try:
            media_id = _twitter_upload_media(media_url)
            if media_id:
                payload["media"] = {"media_ids": [media_id]}
        except Exception as e:
            logger.warning("Twitter media upload failed, posting without media: %s", e)

    auth = _twitter_oauth1_header("POST", _TWITTER_V2_TWEET_URL)

    try:
        # If auth is an OAuth1 object (from requests_oauthlib), use it directly
        if isinstance(auth, str):
            resp = requests.post(
                _TWITTER_V2_TWEET_URL,
                json=payload,
                headers={"Authorization": auth, "Content-Type": "application/json"},
                timeout=30,
            )
        else:
            # requests_oauthlib OAuth1 object
            resp = requests.post(
                _TWITTER_V2_TWEET_URL,
                json=payload,
                auth=auth,
                timeout=30,
            )
    except requests.RequestException as e:
        return f"Error posting to Twitter: {e}"

    if resp.status_code == 201:
        data = resp.json().get("data", {})
        tweet_id = data.get("id", "unknown")
        return (
            f"Tweet posted successfully!\n"
            f"  ID: {tweet_id}\n"
            f"  URL: https://twitter.com/i/web/status/{tweet_id}\n"
            f"  Text: \"{text[:80]}{'...' if len(text) > 80 else ''}\""
        )
    elif resp.status_code == 403:
        return (
            f"Twitter API returned 403 Forbidden. Check your app permissions "
            f"(need Read+Write). Response: {resp.text[:300]}"
        )
    elif resp.status_code == 429:
        return "Twitter API rate limit exceeded. Try again in a few minutes."
    else:
        return f"Twitter API error (HTTP {resp.status_code}): {resp.text[:400]}"


def _twitter_upload_media(media_url: str) -> Optional[str]:
    """Download an image from URL and upload to Twitter, returning media_id_string."""
    img_resp = requests.get(media_url, timeout=30)
    img_resp.raise_for_status()

    auth = _twitter_oauth1_header("POST", _TWITTER_UPLOAD_URL)

    if isinstance(auth, str):
        resp = requests.post(
            _TWITTER_UPLOAD_URL,
            headers={"Authorization": auth},
            files={"media_data": base64.b64encode(img_resp.content)},
            timeout=60,
        )
    else:
        resp = requests.post(
            _TWITTER_UPLOAD_URL,
            auth=auth,
            files={"media_data": base64.b64encode(img_resp.content)},
            timeout=60,
        )

    if resp.status_code == 200:
        return resp.json().get("media_id_string")
    logger.warning("Twitter media upload returned %d: %s", resp.status_code, resp.text[:200])
    return None


# ---------------------------------------------------------------------------
# LinkedIn Direct Posting
# ---------------------------------------------------------------------------

_LINKEDIN_UGC_URL = "https://api.linkedin.com/v2/ugcPosts"


def _linkedin_token_present() -> bool:
    return bool(_get_env("LINKEDIN_ACCESS_TOKEN"))


def linkedin_post_fn(text: str) -> str:
    """Post to LinkedIn via the Marketing API (UGC Posts)."""
    token = _get_env("LINKEDIN_ACCESS_TOKEN")
    if not token:
        return (
            "Error: LINKEDIN_ACCESS_TOKEN not configured.\n"
            "Add to ~/.hermes/.env:\n"
            "  LINKEDIN_ACCESS_TOKEN=<your token>\n"
            "Get a token via LinkedIn Developer Portal: "
            "https://www.linkedin.com/developers/apps"
        )

    # First, resolve the author URN (current user)
    try:
        me_resp = requests.get(
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        me_resp.raise_for_status()
        person_id = me_resp.json().get("id")
        if not person_id:
            return "Error: Could not resolve LinkedIn profile ID from /v2/me."
        author_urn = f"urn:li:person:{person_id}"
    except requests.RequestException as e:
        return f"Error fetching LinkedIn profile: {e}"

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    try:
        resp = requests.post(
            _LINKEDIN_UGC_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            timeout=30,
        )
    except requests.RequestException as e:
        return f"Error posting to LinkedIn: {e}"

    if resp.status_code == 201:
        post_id = resp.headers.get("X-RestLi-Id", resp.json().get("id", "unknown"))
        return (
            f"LinkedIn post published successfully!\n"
            f"  Post ID: {post_id}\n"
            f"  Text: \"{text[:80]}{'...' if len(text) > 80 else ''}\""
        )
    elif resp.status_code == 401:
        return "LinkedIn token expired or invalid. Refresh it and update ~/.hermes/.env."
    elif resp.status_code == 403:
        return f"LinkedIn 403 — check token scopes (need w_member_social). {resp.text[:200]}"
    elif resp.status_code == 429:
        return "LinkedIn rate limit exceeded. Try again later."
    else:
        return f"LinkedIn API error (HTTP {resp.status_code}): {resp.text[:400]}"


# ---------------------------------------------------------------------------
# Smart Auto-Post (routes to best available method)
# ---------------------------------------------------------------------------


def social_post_auto_fn(
    text: str,
    platforms: Optional[List[str]] = None,
    media_url: Optional[str] = None,
) -> str:
    """Smart auto-post: routes to best available method per platform."""
    if not platforms:
        platforms = ["twitter", "linkedin"]

    results: List[str] = []
    any_posted = False

    for plat in platforms:
        plat_lower = plat.lower().strip()

        if plat_lower in ("twitter", "x"):
            # Prefer direct Twitter API if keys present
            if _twitter_keys_present():
                result = twitter_post_fn(text, media_url=media_url)
                results.append(f"[Twitter/X - Direct API] {result}")
                any_posted = True
            elif _get_token():
                result = social_post_fn(text, platform="twitter", media_url=media_url)
                results.append(f"[Twitter/X - Buffer] {result}")
                any_posted = True
            else:
                results.append(
                    "[Twitter/X] Not configured. Set either:\n"
                    "  - TWITTER_API_KEY + TWITTER_API_SECRET + TWITTER_ACCESS_TOKEN + TWITTER_ACCESS_SECRET (direct)\n"
                    "  - BUFFER_API_TOKEN (via Buffer)"
                )

        elif plat_lower == "linkedin":
            if _linkedin_token_present():
                result = linkedin_post_fn(text)
                results.append(f"[LinkedIn - Direct API] {result}")
                any_posted = True
            elif _get_token():
                result = social_post_fn(text, platform="linkedin", media_url=media_url)
                results.append(f"[LinkedIn - Buffer] {result}")
                any_posted = True
            else:
                results.append(
                    "[LinkedIn] Not configured. Set either:\n"
                    "  - LINKEDIN_ACCESS_TOKEN (direct)\n"
                    "  - BUFFER_API_TOKEN (via Buffer)"
                )

        elif plat_lower in ("facebook", "instagram", "pinterest"):
            # These only go through Buffer
            if _get_token():
                result = social_post_fn(text, platform=plat_lower, media_url=media_url)
                results.append(f"[{plat.title()} - Buffer] {result}")
                any_posted = True
            else:
                results.append(
                    f"[{plat.title()}] Not configured. Set BUFFER_API_TOKEN "
                    f"in ~/.hermes/.env to post to {plat.title()} via Buffer."
                )
        else:
            results.append(
                f"[{plat}] Unknown platform. Supported: twitter, linkedin, facebook, instagram, pinterest"
            )

    if not any_posted:
        results.append(
            "\n--- Setup Guide ---\n"
            "No social media accounts are configured. Add credentials to ~/.hermes/.env:\n\n"
            "# Buffer (multi-platform scheduling)\n"
            "BUFFER_API_TOKEN=<token from https://publish.buffer.com/profile/preferences/apps>\n\n"
            "# Twitter/X (direct posting)\n"
            "TWITTER_API_KEY=<consumer key>\n"
            "TWITTER_API_SECRET=<consumer secret>\n"
            "TWITTER_ACCESS_TOKEN=<access token>\n"
            "TWITTER_ACCESS_SECRET=<access token secret>\n\n"
            "# LinkedIn (direct posting)\n"
            "LINKEDIN_ACCESS_TOKEN=<token from https://www.linkedin.com/developers/apps>"
        )

    return "\n\n".join(results)


# ---------------------------------------------------------------------------
# Content Writer (zero API keys needed)
# ---------------------------------------------------------------------------

_PLATFORM_LIMITS = {
    "twitter": 280,
    "x": 280,
    "linkedin": 3000,
    "facebook": 63206,
    "instagram": 2200,
    "pinterest": 500,
}

_PLATFORM_BEST_PRACTICES = {
    "twitter": [
        "Keep it punchy — 100-200 chars performs best",
        "Use 1-3 relevant hashtags max",
        "Ask questions to drive engagement",
        "Thread long-form content",
        "Include a clear CTA",
    ],
    "linkedin": [
        "Open with a hook (first 2 lines are visible before 'see more')",
        "Use line breaks for readability",
        "3-5 relevant hashtags at the end",
        "Tell stories — personal experiences perform well",
        "End with a question to encourage comments",
    ],
    "facebook": [
        "Shorter posts (40-80 chars) get more engagement",
        "Use emojis sparingly for visual breaks",
        "Ask questions or create polls",
        "Share behind-the-scenes content",
        "Post at peak times (noon-3pm)",
    ],
    "instagram": [
        "First line is the hook (shows in feed)",
        "Use 20-30 hashtags for discovery",
        "Include a CTA (save, share, comment)",
        "Use line breaks with dots for spacing",
        "Mix broad and niche hashtags",
    ],
}

_CAPTION_TEMPLATES = {
    "twitter": [
        "{hook}\n\n{key_point}\n\n{cta}\n\n{hashtags}",
        "{question}\n\n{insight}\n\n{hashtags}",
        "{bold_statement}\n\nHere's why: {explanation}\n\n{hashtags}",
        "{statistic}\n\n{takeaway}\n\n{cta} {hashtags}",
        "Thread: {topic_hook}\n\n1/ {point_one}",
    ],
    "linkedin": [
        "{hook}\n\n{story}\n\n{lesson}\n\n{cta}\n\n{hashtags}",
        "{question}\n\n{context}\n\n{insight}\n\n{hashtags}",
        "{bold_claim}\n\nHere's what I've learned:\n\n{points}\n\n{cta}\n\n{hashtags}",
        "I used to think {old_belief}.\n\nThen I discovered {new_insight}.\n\n{takeaway}\n\n{hashtags}",
        "{statistic}\n\n{analysis}\n\nWhat this means for you:\n{action_items}\n\n{hashtags}",
    ],
    "instagram": [
        "{hook}\n.\n.\n{body}\n.\n{cta}\n.\n.\n{hashtags}",
        "{question}\n.\n.\n{answer}\n.\n{cta}\n.\n.\n{hashtags}",
        "{story_hook}\n.\n.\n{story}\n.\n{lesson}\n.\n.\n{hashtags}",
        "{bold_statement}\n.\n.\n{explanation}\n.\n{cta}\n.\n.\n{hashtags}",
        "Save this for later!\n.\n{tips}\n.\n{cta}\n.\n.\n{hashtags}",
    ],
    "facebook": [
        "{question}\n\n{context}\n\n{cta}",
        "{hook}\n\n{value}\n\n{cta}",
        "{bold_statement}\n\n{supporting_points}\n\nWhat do you think?",
        "{personal_story}\n\n{lesson}\n\n{question}",
        "{statistic}\n\n{analysis}\n\n{cta}",
    ],
}


def social_content_fn(
    topic: str,
    platform: str = "twitter",
    count: int = 5,
) -> str:
    """Generate ready-to-post social media captions with hashtags.

    Uses heuristic templates — no API keys required.
    """
    plat = platform.lower().strip()
    char_limit = _PLATFORM_LIMITS.get(plat, 280)
    practices = _PLATFORM_BEST_PRACTICES.get(plat, _PLATFORM_BEST_PRACTICES["twitter"])
    templates = _CAPTION_TEMPLATES.get(plat, _CAPTION_TEMPLATES["twitter"])

    # Generate hashtags from topic words
    words = [w.strip(".,!?;:") for w in topic.split() if len(w) > 2]
    hashtags_list = [f"#{w.title().replace(' ', '')}" for w in words[:3]]
    hashtags_list.extend([f"#{plat.title()}", "#ContentCreation"])
    if plat in ("twitter", "x"):
        hashtags_list = hashtags_list[:3]  # Twitter: fewer hashtags
    hashtags_str = " ".join(hashtags_list)

    count = max(1, min(count, 10))

    lines = [
        f"Social media post ideas for: \"{topic}\"",
        f"Platform: {platform.title()} (max {char_limit} chars)",
        f"\nBest practices for {platform.title()}:",
    ]
    for p in practices:
        lines.append(f"  - {p}")

    lines.append(f"\n{'=' * 50}")
    lines.append(f"{count} ready-to-post captions:\n")

    for i in range(count):
        template = templates[i % len(templates)]
        lines.append(f"--- Post {i + 1} ---")

        if plat in ("twitter", "x"):
            captions = [
                f"Did you know? {topic} is transforming how we think about this space.\n\nHere's what matters most.\n\n{hashtags_str}",
                f"The biggest mistake people make with {topic}?\n\nNot starting sooner.\n\n{hashtags_str}",
                f"3 things I wish I knew about {topic} earlier:\n\n1. Start small\n2. Be consistent\n3. Measure everything\n\n{hashtags_str}",
                f"Hot take: {topic} is underrated.\n\nMost people overlook the fundamentals. Don't be most people.\n\n{hashtags_str}",
                f"Want to get better at {topic}?\n\nStart with these basics and build from there.\n\nDrop a comment if you agree.\n\n{hashtags_str}",
            ]
        elif plat == "linkedin":
            captions = [
                f"I've been thinking a lot about {topic} lately.\n\nHere's what stands out:\n\nThe people who succeed aren't necessarily the smartest — they're the most consistent.\n\nWhat's your experience with {topic}?\n\n{hashtags_str}",
                f"{topic} — a thread.\n\nAfter years in this space, here's my honest take:\n\n1. Start before you're ready\n2. Learn from failures fast\n3. Share what you learn\n\nThe last one is what separates good from great.\n\n{hashtags_str}",
                f"Unpopular opinion about {topic}:\n\nMost advice out there is recycled. What actually works is far simpler than people make it.\n\nFocus on fundamentals. Execute consistently. Measure relentlessly.\n\nAgree or disagree? Tell me below.\n\n{hashtags_str}",
                f"I used to struggle with {topic}.\n\nThen I changed my approach:\n- Focused on one thing at a time\n- Asked for feedback early\n- Stayed patient\n\nThe results followed.\n\nWhat shift made the biggest difference for you?\n\n{hashtags_str}",
                f"The future of {topic} is exciting.\n\nBut here's what most people miss:\n\nIt's not about the tools — it's about the thinking behind them.\n\nMaster the principles, and the tools become easy.\n\nSave this post for later.\n\n{hashtags_str}",
            ]
        elif plat == "instagram":
            captions = [
                f"Let's talk about {topic}.\n.\n.\nHere's the truth nobody tells you: consistency beats perfection every single time.\n.\nSave this for when you need a reminder.\n.\n.\n{hashtags_str}",
                f"Your guide to {topic} starts here.\n.\n.\nStep 1: Learn the basics\nStep 2: Practice daily\nStep 3: Share your journey\nStep 4: Repeat\n.\nTag someone who needs this.\n.\n.\n{hashtags_str}",
                f"The secret to mastering {topic}?\n.\n.\nThere is no secret. It's just showing up every day and doing the work.\n.\nDouble tap if you agree.\n.\n.\n{hashtags_str}",
                f"3 myths about {topic} debunked:\n.\n.\n1. You need to be an expert to start\n2. Results come overnight\n3. You have to do it alone\n.\nNone of these are true. Start today.\n.\n.\n{hashtags_str}",
                f"Save this for later!\n.\n.\n5 tips for {topic}:\n1. Start small\n2. Be consistent\n3. Track progress\n4. Learn from others\n5. Enjoy the process\n.\nWhich one resonates most? Comment below.\n.\n.\n{hashtags_str}",
            ]
        else:
            captions = [
                f"What's your take on {topic}? We'd love to hear your thoughts!\n\n{hashtags_str}",
                f"Here's something interesting about {topic} that most people don't know.\n\nShare this with someone who needs to see it.\n\n{hashtags_str}",
                f"The best advice we've heard about {topic}: start before you're ready.\n\nWhat would you add?\n\n{hashtags_str}",
                f"Breaking down {topic} into simple terms.\n\n1. Understand the basics\n2. Apply what you learn\n3. Share your results\n\nWhich step are you on?\n\n{hashtags_str}",
                f"Big things happening in {topic}!\n\nStay tuned for more updates. In the meantime, what excites you most?\n\n{hashtags_str}",
            ]

        caption = captions[i % len(captions)]
        # Trim to platform limit
        if len(caption) > char_limit:
            caption = caption[: char_limit - 3] + "..."

        lines.append(caption)
        lines.append(f"\n  [{len(caption)} chars / {char_limit} limit]\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------


def _check_buffer_available():
    """Return (available: bool, reason: str) for toolset gating."""
    if _get_token():
        return (True, "BUFFER_API_TOKEN is set")
    return (False, "BUFFER_API_TOKEN not set — social media tools disabled")


def _check_twitter_available():
    if _twitter_keys_present():
        return (True, "Twitter API keys are set")
    return (False, "Twitter API keys not set — set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET")


def _check_linkedin_available():
    if _linkedin_token_present():
        return (True, "LINKEDIN_ACCESS_TOKEN is set")
    return (False, "LINKEDIN_ACCESS_TOKEN not set")


def _check_auto_post_available():
    """Auto-post is always available (returns setup instructions if no keys)."""
    return (True, "Smart auto-post always available")


def _check_content_available():
    """Content generation is always available (no API keys needed)."""
    return (True, "Content writer needs no API keys")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

registry.register(
    name="social_profiles",
    toolset="social_media",
    schema={
        "name": "social_profiles",
        "description": (
            "List all connected social media profiles from Buffer "
            "(profile ID, service name, formatted name, follower count). "
            "Use this to discover profile IDs needed by other social media tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    handler=lambda args, **kw: social_profiles_fn(),
    check_fn=_check_buffer_available,
    requires_env=["BUFFER_API_TOKEN"],
)

registry.register(
    name="social_post",
    toolset="social_media",
    schema={
        "name": "social_post",
        "description": (
            "Create or schedule a social media post via Buffer. "
            "Provide profile_ids or platform (e.g. 'twitter', 'facebook', 'instagram', 'linkedin'). "
            "If scheduled_at is set (ISO 8601 datetime or Unix timestamp), the post is scheduled; "
            "otherwise it's added to the Buffer queue. Optionally attach media via media_url."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The post text/caption."},
                "profile_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Buffer profile IDs to post to. Use social_profiles to find IDs.",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform name (twitter, facebook, instagram, linkedin). Auto-resolves profile IDs if profile_ids not given.",
                },
                "scheduled_at": {
                    "type": "string",
                    "description": "When to publish. ISO 8601 datetime (e.g. '2025-01-15T14:00:00Z') or Unix timestamp. Omit to add to queue.",
                },
                "media_url": {
                    "type": "string",
                    "description": "URL of an image to attach to the post.",
                },
            },
            "required": ["text"],
        },
    },
    handler=lambda args, **kw: social_post_fn(
        text=args["text"],
        profile_ids=args.get("profile_ids"),
        platform=args.get("platform"),
        scheduled_at=args.get("scheduled_at"),
        media_url=args.get("media_url"),
    ),
    check_fn=_check_buffer_available,
    requires_env=["BUFFER_API_TOKEN"],
)

registry.register(
    name="social_queue",
    toolset="social_media",
    schema={
        "name": "social_queue",
        "description": (
            "List pending/scheduled posts in the Buffer queue. "
            "Shows all profiles' queues if no profile_id given."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "Buffer profile ID to show queue for. Omit to show all profiles.",
                },
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: social_queue_fn(
        profile_id=args.get("profile_id"),
    ),
    check_fn=_check_buffer_available,
    requires_env=["BUFFER_API_TOKEN"],
)

registry.register(
    name="social_analytics",
    toolset="social_media",
    schema={
        "name": "social_analytics",
        "description": (
            "Get recent sent posts with engagement stats (likes, comments, shares, clicks) "
            "for a Buffer profile. Shows per-post breakdown and totals."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "Buffer profile ID to get analytics for. Use social_profiles to find IDs.",
                },
            },
            "required": ["profile_id"],
        },
    },
    handler=lambda args, **kw: social_analytics_fn(
        profile_id=args.get("profile_id", ""),
    ),
    check_fn=_check_buffer_available,
    requires_env=["BUFFER_API_TOKEN"],
)

# --- Direct Twitter posting ---
registry.register(
    name="twitter_post",
    toolset="social_media_direct",
    schema={
        "name": "twitter_post",
        "description": (
            "Post a tweet directly to Twitter/X using the Twitter API v2. "
            "Supports text and optional image via media_url. "
            "Requires TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The tweet text (max 280 characters).",
                },
                "media_url": {
                    "type": "string",
                    "description": "Optional URL of an image to attach to the tweet.",
                },
            },
            "required": ["text"],
        },
    },
    handler=lambda args, **kw: twitter_post_fn(
        text=args["text"],
        media_url=args.get("media_url"),
    ),
    check_fn=_check_twitter_available,
    requires_env=["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"],
)

# --- Direct LinkedIn posting ---
registry.register(
    name="linkedin_post",
    toolset="social_media_direct",
    schema={
        "name": "linkedin_post",
        "description": (
            "Publish a post directly to LinkedIn using the Marketing API (UGC Posts). "
            "Requires LINKEDIN_ACCESS_TOKEN."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The post text (max 3000 characters).",
                },
            },
            "required": ["text"],
        },
    },
    handler=lambda args, **kw: linkedin_post_fn(text=args["text"]),
    check_fn=_check_linkedin_available,
    requires_env=["LINKEDIN_ACCESS_TOKEN"],
)

# --- Smart auto-post (always available) ---
registry.register(
    name="social_post_auto",
    toolset="social_media_direct",
    schema={
        "name": "social_post_auto",
        "description": (
            "Smart auto-post: automatically routes to the best available posting method per platform. "
            "Uses direct Twitter API if keys are set, direct LinkedIn API if token is set, "
            "or falls back to Buffer. If nothing is configured, returns setup instructions. "
            "Supports: twitter, linkedin, facebook, instagram, pinterest."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The post text.",
                },
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of platforms to post to (e.g. ['twitter', 'linkedin']). Defaults to twitter + linkedin.",
                },
                "media_url": {
                    "type": "string",
                    "description": "Optional URL of an image to attach (supported on Twitter and Buffer platforms).",
                },
            },
            "required": ["text"],
        },
    },
    handler=lambda args, **kw: social_post_auto_fn(
        text=args["text"],
        platforms=args.get("platforms"),
        media_url=args.get("media_url"),
    ),
    check_fn=_check_auto_post_available,
)

# --- Content writer (zero API keys) ---
registry.register(
    name="social_content",
    toolset="social_media_direct",
    schema={
        "name": "social_content",
        "description": (
            "Generate ready-to-post social media captions with hashtags. "
            "No API keys required — uses heuristic templates tailored to each platform's "
            "character limits and best practices. Great for brainstorming content ideas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic or subject to generate posts about.",
                },
                "platform": {
                    "type": "string",
                    "description": "Target platform: twitter, linkedin, instagram, or facebook. Defaults to twitter.",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of post ideas to generate (1-10). Defaults to 5.",
                },
            },
            "required": ["topic"],
        },
    },
    handler=lambda args, **kw: social_content_fn(
        topic=args["topic"],
        platform=args.get("platform", "twitter"),
        count=args.get("count", 5),
    ),
    check_fn=_check_content_available,
)
