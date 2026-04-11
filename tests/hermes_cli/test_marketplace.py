"""Unit tests for hermes_cli.marketplace — community index fetch + install.

All network calls are mocked; no real HTTP requests made.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_INDEX = {
    "version": 1,
    "updated_at": "2026-01-01T00:00:00Z",
    "skills": [
        {
            "id": "proposal-writer",
            "name": "Proposal Writer",
            "description": "Generates client proposals",
            "author": "Alice",
            "version": "1.0.0",
            "tags": ["writing", "business"],
            "url": "https://example.com/proposal-writer/SKILL.md",
            "homepage": "https://github.com/example/proposal-writer",
        },
        {
            "id": "git-helper",
            "name": "Git Helper",
            "description": "Simplifies common git workflows",
            "author": "Bob",
            "version": "2.1.0",
            "tags": ["dev", "git"],
            "url": "https://example.com/git-helper/SKILL.md",
        },
    ],
}


def _mock_urlopen(content: bytes):
    """Return a context-manager mock for urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = content
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch("urllib.request.urlopen", return_value=mock_resp)


# ---------------------------------------------------------------------------
# fetch_index
# ---------------------------------------------------------------------------

class TestFetchIndex:
    def test_parses_skills(self):
        from hermes_cli.marketplace import fetch_index
        raw = json.dumps(_SAMPLE_INDEX).encode()
        with _mock_urlopen(raw):
            index = fetch_index("https://fake/index.json")
        assert len(index.skills) == 2
        assert index.skills[0].id == "proposal-writer"
        assert index.skills[1].author == "Bob"

    def test_network_error_raises_marketplace_error(self):
        from hermes_cli.marketplace import fetch_index, MarketplaceError
        with patch("urllib.request.urlopen", side_effect=OSError("no network")):
            with pytest.raises(MarketplaceError):
                fetch_index("https://fake/index.json")

    def test_invalid_json_raises(self):
        from hermes_cli.marketplace import fetch_index, MarketplaceError
        with _mock_urlopen(b"NOT JSON"):
            with pytest.raises(MarketplaceError):
                fetch_index("https://fake/index.json")

    def test_missing_skills_key_returns_empty(self):
        from hermes_cli.marketplace import fetch_index
        raw = json.dumps({"version": 1, "updated_at": ""}).encode()
        with _mock_urlopen(raw):
            index = fetch_index("https://fake/index.json")
        assert index.skills == []

    def test_source_url_stored(self):
        from hermes_cli.marketplace import fetch_index
        raw = json.dumps(_SAMPLE_INDEX).encode()
        with _mock_urlopen(raw):
            index = fetch_index("https://fake/index.json")
        assert index.source_url == "https://fake/index.json"


# ---------------------------------------------------------------------------
# search_index
# ---------------------------------------------------------------------------

class TestSearchIndex:
    def _get_index(self):
        from hermes_cli.marketplace import fetch_index
        raw = json.dumps(_SAMPLE_INDEX).encode()
        with _mock_urlopen(raw):
            return fetch_index("https://fake/index.json")

    def test_empty_query_returns_all(self):
        from hermes_cli.marketplace import search_index
        index = self._get_index()
        assert len(search_index(index, "")) == 2

    def test_query_matches_id(self):
        from hermes_cli.marketplace import search_index
        index = self._get_index()
        results = search_index(index, "proposal")
        assert len(results) == 1
        assert results[0].id == "proposal-writer"

    def test_query_matches_description(self):
        from hermes_cli.marketplace import search_index
        index = self._get_index()
        results = search_index(index, "git workflow")
        assert any(r.id == "git-helper" for r in results)

    def test_tag_filter(self):
        from hermes_cli.marketplace import search_index
        index = self._get_index()
        results = search_index(index, tags=["dev"])
        assert len(results) == 1
        assert results[0].id == "git-helper"

    def test_no_match_returns_empty(self):
        from hermes_cli.marketplace import search_index
        index = self._get_index()
        assert search_index(index, "zzznomatch") == []

    def test_case_insensitive(self):
        from hermes_cli.marketplace import search_index
        index = self._get_index()
        results = search_index(index, "PROPOSAL")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# install_from_entry
# ---------------------------------------------------------------------------

class TestInstallFromEntry:
    def test_successful_install(self, tmp_path):
        from hermes_cli.marketplace import install_from_entry, SkillEntry
        entry = SkillEntry(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            url="https://example.com/SKILL.md",
            version="1.0.0",
            author="Tester",
        )
        skill_content = b"---\nname: test-skill\n---\n# Test"

        with _mock_urlopen(skill_content), \
             patch("hermes_constants.get_hermes_home", return_value=tmp_path), \
             patch("agent.components_registry.register_skill"):
            result = install_from_entry(entry)

        assert result.success is True
        assert (tmp_path / "skills" / "test-skill" / "SKILL.md").exists()

    def test_no_url_returns_failure(self, tmp_path):
        from hermes_cli.marketplace import install_from_entry, SkillEntry
        entry = SkillEntry(id="no-url", name="No URL", description="", url="")
        with patch("hermes_constants.get_hermes_home", return_value=tmp_path):
            result = install_from_entry(entry)
        assert result.success is False
        assert "No download URL" in result.error

    def test_already_installed_without_force(self, tmp_path):
        from hermes_cli.marketplace import install_from_entry, SkillEntry
        skill_dir = tmp_path / "skills" / "existing"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("existing", encoding="utf-8")

        entry = SkillEntry(
            id="existing", name="Existing", description="",
            url="https://example.com/SKILL.md",
        )
        with patch("hermes_constants.get_hermes_home", return_value=tmp_path):
            result = install_from_entry(entry, force=False)
        assert result.success is False
        assert "Already installed" in result.error

    def test_force_overwrites(self, tmp_path):
        from hermes_cli.marketplace import install_from_entry, SkillEntry
        skill_dir = tmp_path / "skills" / "overwrite-me"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("old", encoding="utf-8")

        entry = SkillEntry(
            id="overwrite-me", name="Overwrite", description="",
            url="https://example.com/SKILL.md",
        )
        with _mock_urlopen(b"new content"), \
             patch("hermes_constants.get_hermes_home", return_value=tmp_path), \
             patch("agent.components_registry.register_skill"):
            result = install_from_entry(entry, force=True)
        assert result.success is True
        assert (tmp_path / "skills" / "overwrite-me" / "SKILL.md").read_text() == "new content"

    def test_download_error_returns_failure(self, tmp_path):
        from hermes_cli.marketplace import install_from_entry, SkillEntry
        entry = SkillEntry(
            id="fail", name="Fail", description="",
            url="https://example.com/SKILL.md",
        )
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")), \
             patch("hermes_constants.get_hermes_home", return_value=tmp_path):
            result = install_from_entry(entry)
        assert result.success is False
        assert "Download failed" in result.error
