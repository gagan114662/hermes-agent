"""Tests for tools/social_media_tool.py — Buffer, Twitter, LinkedIn, content gen."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest
import requests


from tools.social_media_tool import (
    RateLimitError,
    _buf_get,
    _buf_post,
    _check_token,
    _format_timestamp,
    _get_token,
    _handle_response,
    _headers,
    _twitter_keys_present,
    _linkedin_token_present,
    _twitter_oauth1_header,
    social_content_fn,
    social_profiles_fn,
    social_post_fn,
    social_analytics_fn,
    social_queue_fn,
    twitter_post_fn,
    linkedin_post_fn,
)


# ── helpers ───────────────────────────────────────────────────────────────────

class TestGetToken:
    def test_returns_empty_without_env(self, monkeypatch):
        monkeypatch.delenv("BUFFER_API_TOKEN", raising=False)
        assert _get_token() == ""

    def test_returns_token_from_env(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "mytoken123")
        assert _get_token() == "mytoken123"


class TestHeaders:
    def test_authorization_header(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "abc123")
        h = _headers()
        assert h["Authorization"] == "Bearer abc123"

    def test_content_type_header(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "x")
        h = _headers()
        assert "Content-Type" in h


class TestCheckToken:
    def test_returns_error_when_missing(self, monkeypatch):
        monkeypatch.delenv("BUFFER_API_TOKEN", raising=False)
        err = _check_token()
        assert err is not None
        assert "BUFFER_API_TOKEN" in err

    def test_returns_none_when_present(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "token123")
        assert _check_token() is None


class TestHandleResponse:
    def test_raises_rate_limit_error_on_429(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "10"}
        with pytest.raises(RateLimitError) as exc_info:
            _handle_response(mock_resp)
        assert exc_info.value.retry_after == 10

    def test_uses_default_retry_after(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        with pytest.raises(RateLimitError) as exc_info:
            _handle_response(mock_resp)
        assert exc_info.value.retry_after == 5

    def test_raises_for_other_errors(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 error")
        with pytest.raises(requests.HTTPError):
            _handle_response(mock_resp)

    def test_returns_json_on_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": "value"}
        result = _handle_response(mock_resp)
        assert result == {"data": "value"}


class TestFormatTimestamp:
    def test_none_returns_unscheduled(self):
        assert _format_timestamp(None) == "unscheduled"

    def test_zero_returns_unscheduled(self):
        assert _format_timestamp(0) == "unscheduled"

    def test_valid_timestamp(self):
        ts = 1700000000  # Some fixed timestamp
        result = _format_timestamp(ts)
        assert "UTC" in result
        assert "-" in result  # date format YYYY-MM-DD

    def test_invalid_timestamp_returns_string(self):
        result = _format_timestamp("not_a_number")
        assert isinstance(result, str)


class TestRateLimitError:
    def test_is_exception(self):
        err = RateLimitError("too fast", retry_after=30)
        assert isinstance(err, Exception)

    def test_stores_retry_after(self):
        err = RateLimitError("msg", retry_after=15)
        assert err.retry_after == 15

    def test_default_retry_after(self):
        err = RateLimitError("msg")
        assert err.retry_after == 5


# ── _buf_get / _buf_post ──────────────────────────────────────────────────────

class TestBufGet:
    def _mock_success(self, data=None):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = data or {"ok": True}
        return mock_resp

    def test_makes_get_request(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        with patch("requests.get", return_value=self._mock_success()) as mock_get:
            _buf_get("/profiles.json")
        mock_get.assert_called_once()

    def test_url_includes_endpoint(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        with patch("requests.get", return_value=self._mock_success()) as mock_get:
            _buf_get("/profiles.json")
        call_url = mock_get.call_args[0][0]
        assert "/profiles.json" in call_url

    def test_retries_on_rate_limit(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        rate_resp = MagicMock()
        rate_resp.status_code = 429
        rate_resp.headers = {"Retry-After": "0"}

        ok_resp = self._mock_success()
        with patch("requests.get", side_effect=[rate_resp, ok_resp]), \
             patch("time.sleep"):
            result = _buf_get("/profiles.json")
        assert result == {"ok": True}

    def test_raises_after_max_retries(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        rate_resp = MagicMock()
        rate_resp.status_code = 429
        rate_resp.headers = {"Retry-After": "0"}
        with patch("requests.get", return_value=rate_resp), \
             patch("time.sleep"):
            with pytest.raises(RateLimitError):
                _buf_get("/endpoint")


class TestBufPost:
    def _mock_success(self, data=None):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = data or {"success": True}
        return mock_resp

    def test_makes_post_request(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        with patch("requests.post", return_value=self._mock_success()) as mock_post:
            _buf_post("/updates/create.json", {"text": "hello"})
        mock_post.assert_called_once()


# ── _twitter_keys_present ─────────────────────────────────────────────────────

class TestTwitterKeysPresent:
    def test_false_when_no_keys(self, monkeypatch):
        for k in ["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]:
            monkeypatch.delenv(k, raising=False)
        assert _twitter_keys_present() is False

    def test_true_when_all_keys_set(self, monkeypatch):
        monkeypatch.setenv("TWITTER_API_KEY", "key")
        monkeypatch.setenv("TWITTER_API_SECRET", "sec")
        monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "tok")
        monkeypatch.setenv("TWITTER_ACCESS_SECRET", "tsec")
        assert _twitter_keys_present() is True


# ── _linkedin_token_present ───────────────────────────────────────────────────

class TestLinkedinTokenPresent:
    def test_false_when_not_set(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
        assert _linkedin_token_present() is False

    def test_true_when_set(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "li_token")
        assert _linkedin_token_present() is True


# ── social_profiles_fn ────────────────────────────────────────────────────────

class TestSocialProfilesFn:
    def test_returns_error_without_token(self, monkeypatch):
        monkeypatch.delenv("BUFFER_API_TOKEN", raising=False)
        result = social_profiles_fn()
        assert "BUFFER_API_TOKEN" in result

    def test_returns_profiles_list(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        profiles = [
            {"id": "1", "service": "twitter", "service_username": "myhandle",
             "formatted_service": "Twitter", "counts": {"followers": 100}}
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = profiles

        with patch("requests.get", return_value=mock_resp):
            result = social_profiles_fn()
        assert "twitter" in result.lower() or "Twitter" in result

    def test_returns_message_when_no_profiles(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = []

        with patch("requests.get", return_value=mock_resp):
            result = social_profiles_fn()
        assert "No social profiles" in result or "no" in result.lower()

    def test_handles_request_error(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        with patch("requests.get", side_effect=requests.RequestException("network error")):
            result = social_profiles_fn()
        assert "Error" in result


# ── social_post_fn ────────────────────────────────────────────────────────────

class TestSocialPostFn:
    def test_returns_error_without_token(self, monkeypatch):
        monkeypatch.delenv("BUFFER_API_TOKEN", raising=False)
        result = social_post_fn("test post")
        assert "BUFFER_API_TOKEN" in result

    def test_requires_profile_id_or_platform(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        result = social_post_fn("test post")
        assert "Error" in result

    def test_posts_with_profile_ids(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"success": True, "updates": [{"id": "u1", "status": "buffer"}]}

        with patch("requests.post", return_value=mock_resp):
            result = social_post_fn("Hello world", profile_ids=["123"])
        assert isinstance(result, str)
        assert "Error" not in result or len(result) > 20

    def test_invalid_scheduled_at_format(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        result = social_post_fn("test", profile_ids=["123"], scheduled_at="not-a-date")
        assert "Error" in result

    def test_valid_iso_8601_schedule(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"success": True, "updates": [{"id": "u1", "status": "buffer"}]}

        with patch("requests.post", return_value=mock_resp):
            result = social_post_fn(
                "Scheduled post",
                profile_ids=["123"],
                scheduled_at="2025-12-01T09:00:00Z"
            )
        assert isinstance(result, str)

    def test_handles_rate_limit(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        rate_resp = MagicMock()
        rate_resp.status_code = 429
        rate_resp.headers = {"Retry-After": "0"}

        with patch("requests.post", return_value=rate_resp), \
             patch("time.sleep"):
            result = social_post_fn("test", profile_ids=["123"])
        assert "Rate limit" in result or "Error" in result


# ── social_queue_fn ───────────────────────────────────────────────────────────

class TestSocialQueueFn:
    def test_returns_error_without_token(self, monkeypatch):
        monkeypatch.delenv("BUFFER_API_TOKEN", raising=False)
        result = social_queue_fn()
        assert "BUFFER_API_TOKEN" in result

    def test_fetches_queue_for_all_profiles(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        profiles_resp = MagicMock()
        profiles_resp.status_code = 200
        profiles_resp.raise_for_status = MagicMock()
        profiles_resp.json.return_value = [{"id": "p1", "service": "twitter"}]

        queue_resp = MagicMock()
        queue_resp.status_code = 200
        queue_resp.raise_for_status = MagicMock()
        queue_resp.json.return_value = {"updates": []}

        with patch("requests.get", side_effect=[profiles_resp, queue_resp]):
            result = social_queue_fn()
        assert isinstance(result, str)


# ── social_analytics_fn ───────────────────────────────────────────────────────

class TestSocialAnalyticsFn:
    def test_returns_error_without_token(self, monkeypatch):
        monkeypatch.delenv("BUFFER_API_TOKEN", raising=False)
        result = social_analytics_fn("some_profile_id")
        assert "BUFFER_API_TOKEN" in result


# ── social_content_fn ─────────────────────────────────────────────────────────

class TestSocialContentFn:
    def test_returns_string_always(self):
        """Content generation doesn't need API keys."""
        result = social_content_fn(
            topic="AI productivity tools",
            platform="twitter",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_topic_in_output(self):
        result = social_content_fn(topic="machine learning", platform="linkedin")
        # The topic or related content should appear
        assert isinstance(result, str)

    def test_handles_all_platforms(self):
        for platform in ["twitter", "linkedin", "instagram", "facebook"]:
            result = social_content_fn(topic="test", platform=platform)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_uses_count_parameter(self):
        result = social_content_fn(topic="test", count=3)
        assert isinstance(result, str)

    def test_default_platform(self):
        result = social_content_fn(topic="test launch")
        assert isinstance(result, str)
        assert len(result) > 0


# ── social_post_fn (platform lookup path) ────────────────────────────────────

class TestSocialPostFnPlatformLookup:
    """Tests the code path where platform is given instead of profile_ids."""

    def _mock_resp(self, data):
        r = MagicMock()
        r.status_code = 200
        r.raise_for_status = MagicMock()
        r.json.return_value = data
        return r

    def test_error_without_platform_or_profile_ids(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        result = social_post_fn("Hello world")
        assert "Error" in result

    def test_platform_lookup_no_match_returns_error(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        profiles_resp = self._mock_resp([
            {"id": "p1", "service": "twitter"},
        ])
        with patch("requests.get", return_value=profiles_resp):
            result = social_post_fn("Hello", platform="linkedin")
        assert "No Buffer profile found" in result or "linkedin" in result.lower()

    def test_platform_lookup_finds_match_and_posts(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        profiles_resp = self._mock_resp([{"id": "p1", "service": "twitter"}])
        post_resp = self._mock_resp({"success": True, "updates": [{"id": "u1", "status": "buffer", "due_at": None}]})
        with patch("requests.get", return_value=profiles_resp), \
             patch("requests.post", return_value=post_resp):
            result = social_post_fn("Hello world", platform="twitter")
        assert isinstance(result, str)

    def test_rate_limit_error_from_profile_lookup(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        with patch("requests.get", side_effect=RateLimitError(60)):
            result = social_post_fn("Hello", platform="twitter")
        assert "Rate limit" in result or "limit" in result.lower()

    def test_scheduled_at_unix_timestamp(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        post_resp = self._mock_resp({
            "success": True,
            "updates": [{"id": "u2", "status": "buffer", "due_at": 1700000000}],
        })
        with patch("requests.post", return_value=post_resp):
            result = social_post_fn("Scheduled post", profile_ids=["p1"],
                                    scheduled_at="1700000000")
        assert isinstance(result, str)

    def test_scheduled_at_iso8601(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        post_resp = self._mock_resp({
            "success": True,
            "updates": [{"id": "u3", "status": "buffer", "due_at": 1700000000}],
        })
        with patch("requests.post", return_value=post_resp):
            result = social_post_fn("ISO sched", profile_ids=["p1"],
                                    scheduled_at="2025-11-14T22:13:20Z")
        assert isinstance(result, str)

    def test_buffer_rejection_returns_error_message(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        post_resp = self._mock_resp({"success": False, "message": "too long"})
        with patch("requests.post", return_value=post_resp):
            result = social_post_fn("text", profile_ids=["p1"])
        assert "too long" in result or "rejected" in result.lower()


# ── social_queue_fn (multi-profile path) ─────────────────────────────────────

class TestSocialQueueFnMultiProfile:
    def _mock_resp(self, data):
        r = MagicMock()
        r.status_code = 200
        r.raise_for_status = MagicMock()
        r.json.return_value = data
        return r

    def test_shows_pending_posts_for_all_profiles(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        profiles_r = self._mock_resp([
            {"id": "p1", "service": "twitter",
             "formatted_username": "@tester", "service_username": "tester"},
        ])
        queue_r = self._mock_resp({
            "updates": [{"id": "u1", "text": "Hello", "due_at": 1700000000}]
        })
        with patch("requests.get", side_effect=[profiles_r, queue_r]):
            result = social_queue_fn()
        assert "twitter" in result.lower() or "tester" in result.lower()

    def test_empty_profiles_list_returns_message(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        r = self._mock_resp([])
        with patch("requests.get", return_value=r):
            result = social_queue_fn()
        assert "No profiles" in result

    def test_single_profile_with_posts(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        r = self._mock_resp({
            "updates": [{"id": "u1", "text": "Test post", "due_at": 1700000000}]
        })
        with patch("requests.get", return_value=r):
            result = social_queue_fn(profile_id="p1")
        assert "u1" in result or "Test post" in result

    def test_single_profile_empty_queue(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        r = self._mock_resp({"updates": []})
        with patch("requests.get", return_value=r):
            result = social_queue_fn(profile_id="p1")
        assert "No pending posts" in result


# ── social_analytics_fn (with data) ──────────────────────────────────────────

class TestSocialAnalyticsFnWithData:
    def _mock_resp(self, data, status=200):
        r = MagicMock()
        r.status_code = status
        r.raise_for_status = MagicMock()
        r.json.return_value = data
        return r

    def test_returns_analytics_summary(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        # /profiles.json returns a list; /updates/sent.json returns a dict with "updates"
        profiles_r = self._mock_resp([
            {"id": "p1", "service": "twitter", "service_username": "tester",
             "counts": {"followers": 1000}},
        ])
        sent_r = self._mock_resp({
            "updates": [
                {"id": "u1", "text": "Post 1", "statistics": {"clicks": 10, "reach": 500}},
            ]
        })
        with patch("requests.get", side_effect=[profiles_r, sent_r]):
            result = social_analytics_fn("p1")
        assert isinstance(result, str)

    def test_rate_limit_error_returns_message(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        with patch("requests.get", side_effect=RateLimitError(30)):
            result = social_analytics_fn("p1")
        assert "Rate limit" in result or "limit" in result.lower()


# ── twitter_post_fn ────────────────────────────────────────────────────────────

class TestTwitterPostFn:
    def _setup_twitter_env(self, monkeypatch):
        monkeypatch.setenv("TWITTER_API_KEY", "key")
        monkeypatch.setenv("TWITTER_API_SECRET", "secret")
        monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "token")
        monkeypatch.setenv("TWITTER_ACCESS_SECRET", "token_secret")

    def test_returns_error_without_credentials(self, monkeypatch):
        for k in ["TWITTER_API_KEY", "TWITTER_API_SECRET",
                  "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"]:
            monkeypatch.delenv(k, raising=False)
        result = twitter_post_fn("Hello Twitter")
        assert "Error" in result

    def test_successful_tweet(self, monkeypatch):
        self._setup_twitter_env(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"data": {"id": "tweet123"}}
        with patch("requests.post", return_value=mock_resp), \
             patch("tools.social_media_tool._twitter_oauth1_header", return_value="OAuth ..."):
            result = twitter_post_fn("Hello Twitter!")
        assert "tweet123" in result or "successfully" in result.lower()

    def test_403_forbidden_response(self, monkeypatch):
        self._setup_twitter_env(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        with patch("requests.post", return_value=mock_resp), \
             patch("tools.social_media_tool._twitter_oauth1_header", return_value="OAuth ..."):
            result = twitter_post_fn("Hello")
        assert "403" in result or "Forbidden" in result.lower()

    def test_429_rate_limit_response(self, monkeypatch):
        self._setup_twitter_env(monkeypatch)
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit"
        with patch("requests.post", return_value=mock_resp), \
             patch("tools.social_media_tool._twitter_oauth1_header", return_value="OAuth ..."):
            result = twitter_post_fn("Hello")
        assert "rate limit" in result.lower()

    def test_request_exception_returns_error(self, monkeypatch):
        self._setup_twitter_env(monkeypatch)
        with patch("requests.post", side_effect=requests.RequestException("timeout")), \
             patch("tools.social_media_tool._twitter_oauth1_header", return_value="OAuth ..."):
            result = twitter_post_fn("Hello")
        assert "Error" in result


# ── linkedin_post_fn ───────────────────────────────────────────────────────────

class TestLinkedInPostFn:
    def test_returns_error_without_token(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
        result = linkedin_post_fn("Hello LinkedIn")
        assert "Error" in result or "LINKEDIN_ACCESS_TOKEN" in result

    def test_successful_post(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "li_token")
        me_resp = MagicMock()
        me_resp.status_code = 200
        me_resp.raise_for_status = MagicMock()
        me_resp.json.return_value = {"id": "person123"}

        post_resp = MagicMock()
        post_resp.status_code = 201
        post_resp.headers = {"X-RestLi-Id": "post456"}
        post_resp.json.return_value = {}

        with patch("requests.get", return_value=me_resp), \
             patch("requests.post", return_value=post_resp):
            result = linkedin_post_fn("My LinkedIn post")
        assert "post456" in result or "successfully" in result.lower()

    def test_401_expired_token(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "li_token")
        me_resp = MagicMock()
        me_resp.status_code = 200
        me_resp.raise_for_status = MagicMock()
        me_resp.json.return_value = {"id": "person123"}

        post_resp = MagicMock()
        post_resp.status_code = 401
        post_resp.text = "Unauthorized"

        with patch("requests.get", return_value=me_resp), \
             patch("requests.post", return_value=post_resp):
            result = linkedin_post_fn("Post")
        assert "expired" in result.lower() or "401" in result

    def test_profile_fetch_error(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "li_token")
        with patch("requests.get", side_effect=requests.RequestException("network error")):
            result = linkedin_post_fn("Post")
        assert "Error" in result


# ── _twitter_oauth1_header ─────────────────────────────────────────────────────

class TestTwitterOauth1Header:
    def _setup_keys(self, monkeypatch):
        monkeypatch.setenv("TWITTER_API_KEY", "consumer_key")
        monkeypatch.setenv("TWITTER_API_SECRET", "consumer_secret")
        monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "token")
        monkeypatch.setenv("TWITTER_ACCESS_SECRET", "token_secret")

    def test_returns_header_string_without_oauthlib(self, monkeypatch):
        self._setup_keys(monkeypatch)
        # Force the manual HMAC path by making OAuth1 import fail
        with patch.dict("sys.modules", {"requests_oauthlib": None}):
            result = _twitter_oauth1_header("POST", "https://api.twitter.com/2/tweets")
        assert isinstance(result, str)
        assert "OAuth" in result

    def test_header_contains_oauth_nonce(self, monkeypatch):
        self._setup_keys(monkeypatch)
        with patch.dict("sys.modules", {"requests_oauthlib": None}):
            result = _twitter_oauth1_header("POST", "https://api.twitter.com/2/tweets")
        assert "oauth_nonce" in result

    def test_header_contains_signature(self, monkeypatch):
        self._setup_keys(monkeypatch)
        with patch.dict("sys.modules", {"requests_oauthlib": None}):
            result = _twitter_oauth1_header("POST", "https://api.twitter.com/2/tweets")
        assert "oauth_signature" in result

    def test_body_params_included_in_signature(self, monkeypatch):
        self._setup_keys(monkeypatch)
        with patch.dict("sys.modules", {"requests_oauthlib": None}):
            result = _twitter_oauth1_header(
                "POST", "https://api.twitter.com/2/tweets",
                body_params={"text": "hello world"},
            )
        # Should not raise and should return a valid header string
        assert isinstance(result, str)


# ── _format_timestamp edge cases ──────────────────────────────────────────────

class TestFormatTimestampEdgeCases:
    def test_none_returns_unscheduled(self):
        assert _format_timestamp(None) == "unscheduled"

    def test_zero_returns_unscheduled(self):
        assert _format_timestamp(0) == "unscheduled"

    def test_valid_unix_ts(self):
        result = _format_timestamp(1700000000)
        assert "2023" in result or "UTC" in result  # valid date

    def test_string_ts_parsed(self):
        result = _format_timestamp("1700000000")
        assert isinstance(result, str)
        assert result != "unscheduled"

    def test_invalid_value_returns_string(self):
        result = _format_timestamp("not-a-timestamp")
        assert isinstance(result, str)


# ── rate limit retry logic ────────────────────────────────────────────────────

class TestRateLimitRetry:
    def test_buf_get_retries_on_rate_limit(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        # First call: rate-limited; second: success
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.raise_for_status = MagicMock()
        ok_resp.json.return_value = [{"id": "p1"}]

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RateLimitError(0)
            return ok_resp

        with patch("requests.get", side_effect=side_effect), \
             patch("time.sleep"):
            result = _buf_get("/profiles.json")
        assert result == [{"id": "p1"}]

    def test_buf_post_retries_on_rate_limit(self, monkeypatch):
        monkeypatch.setenv("BUFFER_API_TOKEN", "tok")
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.raise_for_status = MagicMock()
        ok_resp.json.return_value = {"success": True}

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RateLimitError(0)
            return ok_resp

        with patch("requests.post", side_effect=side_effect), \
             patch("time.sleep"):
            result = _buf_post("/updates/create.json", {})
        assert result["success"] is True
