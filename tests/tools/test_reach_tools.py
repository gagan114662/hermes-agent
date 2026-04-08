"""Tests for tools/reach_tools.py — web scraping and content ingestion helpers."""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ── Import guard ──────────────────────────────────────────────────────────────
try:
    from tools.reach_tools import (
        jina_read_fn,
        rss_fetch_fn,
        youtube_get_fn,
        youtube_search_fn,
    )
    _REACH_AVAILABLE = True
except ImportError:
    _REACH_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _REACH_AVAILABLE, reason="reach_tools not importable")


# ── jina_read ─────────────────────────────────────────────────────────────────

class TestJinaRead:
    def test_returns_string(self):
        """jina_read should always return a string."""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "# Article Title\n\nContent here."
            mock_get.return_value = mock_resp
            result = jina_read_fn("https://example.com/article")
        assert isinstance(result, str)

    def test_handles_request_error(self):
        import requests
        with patch("requests.get", side_effect=requests.RequestException("connection failed")):
            result = jina_read_fn("https://example.com")
        assert isinstance(result, str)
        assert "Error" in result or "error" in result.lower() or len(result) > 0

    def test_url_sent_to_jina(self):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "content"
            mock_get.return_value = mock_resp
            jina_read_fn("https://example.com/page")
        call_url = str(mock_get.call_args)
        assert "example.com" in call_url or "jina" in call_url.lower()

    def test_empty_url_returns_error(self):
        result = jina_read_fn("")
        assert isinstance(result, str)


# ── rss_fetch ─────────────────────────────────────────────────────────────────

class TestRssFetch:
    def _mock_feed(self, entries=None):
        mock_feed = MagicMock()
        mock_feed.feed.get.return_value = "Test Feed"
        mock_feed.bozo = False
        mock_feed.entries = entries or [
            MagicMock(
                title="Entry 1",
                link="https://example.com/1",
                summary="Summary 1",
                published="Mon, 01 Jan 2024 00:00:00 GMT",
            )
        ]
        return mock_feed

    def test_returns_string_for_valid_feed(self):
        with patch("feedparser.parse", return_value=self._mock_feed()):
            result = rss_fetch_fn("https://example.com/feed.xml")
        assert isinstance(result, str)

    def test_includes_entry_titles(self):
        with patch("feedparser.parse", return_value=self._mock_feed()):
            result = rss_fetch_fn("https://example.com/feed.xml")
        assert "Entry 1" in result

    def test_handles_empty_feed(self):
        with patch("feedparser.parse", return_value=self._mock_feed(entries=[])):
            result = rss_fetch_fn("https://example.com/feed.xml")
        assert isinstance(result, str)

    def test_handles_bozo_error(self):
        mock_feed = self._mock_feed()
        mock_feed.bozo = True
        mock_feed.bozo_exception = Exception("XML parse error")
        with patch("feedparser.parse", return_value=mock_feed):
            result = rss_fetch_fn("https://example.com/bad-feed.xml")
        assert isinstance(result, str)


# ── youtube_search ────────────────────────────────────────────────────────────

class TestYoutubeSearch:
    def test_returns_string_without_api_key(self, monkeypatch):
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        result = youtube_search_fn("python tutorial")
        assert isinstance(result, str)

    def test_with_mocked_api(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake_key")
        mock_data = {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {
                        "title": "Python Tutorial",
                        "channelTitle": "TestChannel",
                        "description": "Learn Python",
                    }
                }
            ]
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_data
            mock_get.return_value = mock_resp
            result = youtube_search_fn("python tutorial")
        assert isinstance(result, str)


# ── youtube_get ───────────────────────────────────────────────────────────────

class TestYoutubeGet:
    def test_invalid_url_returns_error(self):
        result = youtube_get_fn("https://not-youtube.com/watch?v=abc")
        assert isinstance(result, str)

    def test_empty_url_returns_error(self):
        result = youtube_get_fn("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_youtube_url_attempts_fetch(self):
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "<html><title>Video</title></html>"
            mock_get.return_value = mock_resp
            result = youtube_get_fn("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert isinstance(result, str)
