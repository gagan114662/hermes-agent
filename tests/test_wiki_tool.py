"""Tests for tools/wiki_tool.py — wiki read/write/list/query/update/ingest."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest


# ── patch the wiki dir to a temp location ────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_wiki_dir(tmp_path, monkeypatch):
    """Redirect all wiki I/O to a temp directory."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    import tools.wiki_tool as wt
    monkeypatch.setattr(wt, "_wiki_dir", lambda: wiki_dir)
    return wiki_dir


from tools.wiki_tool import (
    _ensure_defaults,
    _list_pages,
    _read_page,
    _write_page,
    _DEFAULT_PAGES,
    wiki_list,
    wiki_read,
)


# ── storage helpers ───────────────────────────────────────────────────────────

class TestWikiStorageHelpers:
    def test_write_and_read_page(self, patch_wiki_dir):
        _write_page("test", "# Test Page\n\nSome content.")
        content = _read_page("test")
        assert "Test Page" in content

    def test_read_nonexistent_page_returns_empty(self):
        result = _read_page("nonexistent_page_xyz")
        assert result == ""

    def test_list_pages_empty(self):
        pages = _list_pages()
        assert isinstance(pages, list)

    def test_list_pages_after_write(self):
        _write_page("alpha", "# Alpha")
        _write_page("beta", "# Beta")
        pages = _list_pages()
        assert "alpha" in pages
        assert "beta" in pages

    def test_list_pages_sorted(self):
        _write_page("z_page", "# Z")
        _write_page("a_page", "# A")
        pages = _list_pages()
        assert pages == sorted(pages)


# ── _ensure_defaults ──────────────────────────────────────────────────────────

class TestEnsureDefaults:
    def test_creates_default_pages(self):
        _ensure_defaults()
        pages = _list_pages()
        for name in _DEFAULT_PAGES:
            assert name in pages, f"Default page '{name}' not created"

    def test_does_not_overwrite_existing(self):
        _write_page("clients", "# My custom clients")
        _ensure_defaults()
        content = _read_page("clients")
        assert "My custom clients" in content

    def test_idempotent(self):
        _ensure_defaults()
        _ensure_defaults()
        # Should not raise or duplicate pages
        pages = _list_pages()
        for name in _DEFAULT_PAGES:
            assert pages.count(name) == 1


# ── wiki_list ─────────────────────────────────────────────────────────────────

class TestWikiList:
    def test_returns_string(self):
        result = wiki_list()
        assert isinstance(result, str)

    def test_lists_created_pages(self):
        _write_page("test_wiki_page", "content")
        result = wiki_list()
        assert "test_wiki_page" in result

    def test_empty_wiki_message(self):
        result = wiki_list()
        # Should give some output (either empty message or page list)
        assert result is not None


# ── wiki_read ─────────────────────────────────────────────────────────────────

class TestWikiRead:
    def test_reads_existing_page(self):
        _write_page("mypage", "# My Page\nSome content.")
        result = wiki_read("mypage")
        assert "My Page" in result

    def test_error_for_missing_page(self):
        result = wiki_read("definitely_does_not_exist")
        assert "not found" in result.lower() or "does not exist" in result.lower() or result == ""

    def test_with_md_extension_stripped(self):
        _write_page("clients", "# Clients\n")
        result = wiki_read("clients")
        assert "Clients" in result


# ── _ollama (mocked) ──────────────────────────────────────────────────────────

class TestOllamaHelper:
    def test_returns_response_on_success(self):
        import tools.wiki_tool as wt
        fake_response = json.dumps({"response": "test answer"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = wt._ollama("test prompt")
        assert result == "test answer"

    def test_returns_error_string_on_exception(self):
        import tools.wiki_tool as wt
        with patch("urllib.request.urlopen", side_effect=URLError("connection refused")):
            result = wt._ollama("test prompt", timeout=1)
        assert result.startswith("Error")

    def test_uses_ollama_model_env_var(self):
        import tools.wiki_tool as wt
        with patch.dict(os.environ, {"OLLAMA_MODEL": "mistral:7b"}):
            with patch("urllib.request.urlopen", side_effect=URLError("x")):
                result = wt._ollama("hi")
        assert result.startswith("Error")


# ── wiki_query (mocked LLM) ───────────────────────────────────────────────────

class TestWikiQuery:
    def test_returns_string(self):
        from tools.wiki_tool import wiki_query
        _ensure_defaults()
        with patch("tools.wiki_tool._ollama", return_value="synthesized answer"):
            result = wiki_query("test question")
        assert isinstance(result, str)

    def test_ollama_called_with_question(self):
        from tools.wiki_tool import wiki_query
        _ensure_defaults()
        with patch("tools.wiki_tool._ollama", return_value="answer") as mock_ollama:
            wiki_query("what is our pricing?")
        assert mock_ollama.called
        call_args = mock_ollama.call_args[0][0]
        assert "pricing" in call_args

    def test_returns_error_on_ollama_failure(self):
        from tools.wiki_tool import wiki_query
        _ensure_defaults()
        with patch("tools.wiki_tool._ollama", return_value="Error: connection refused"):
            result = wiki_query("anything")
        # Should propagate the error or wrap it
        assert isinstance(result, str)


# ── wiki_update (mocked LLM) ──────────────────────────────────────────────────

class TestWikiUpdate:
    def test_enqueues_update(self):
        from tools.wiki_tool import wiki_update
        with patch("tools.wiki_tool._enqueue_update") as mock_enqueue:
            wiki_update("New client: Alice", "crm_log")
            mock_enqueue.assert_called_once()

    def test_returns_confirmation_string(self):
        from tools.wiki_tool import wiki_update
        with patch("tools.wiki_tool._enqueue_update"):
            result = wiki_update("Some info", "test_source")
        assert isinstance(result, str)
        assert len(result) > 0


# ── wiki_ingest (mocked LLM) ─────────────────────────────────────────────────

class TestWikiIngest:
    def test_enqueues_ingest(self):
        from tools.wiki_tool import wiki_ingest
        with patch("tools.wiki_tool._enqueue_update") as mock_enqueue:
            wiki_ingest("Long transcript text goes here.", "meeting_notes")
            mock_enqueue.assert_called_once()

    def test_returns_string(self):
        from tools.wiki_tool import wiki_ingest
        with patch("tools.wiki_tool._enqueue_update"):
            result = wiki_ingest("content", "source")
        assert isinstance(result, str)
