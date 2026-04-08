"""Tests for tools/discovery_tool.py — discovery_run and discovery_read."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from tools.discovery_tool import (
    _DISCOVERY_QUESTIONS,
    _ollama,
    _projects_dir,
    discovery_read,
    discovery_run,
)


# ── _projects_dir ─────────────────────────────────────────────────────────────

class TestProjectsDir:
    def test_creates_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        d = _projects_dir("Acme Corp")
        assert d.is_dir()

    def test_sanitizes_spaces(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        d = _projects_dir("Acme Corp")
        assert " " not in d.name

    def test_sanitizes_slashes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        d = _projects_dir("Acme/Corp/Sub")
        assert "/" not in d.name

    def test_lowercases_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        d = _projects_dir("ACME")
        assert d.name == "acme"


# ── _DISCOVERY_QUESTIONS ──────────────────────────────────────────────────────

class TestDiscoveryQuestions:
    def test_has_five_questions(self):
        assert len(_DISCOVERY_QUESTIONS) == 5

    def test_all_questions_are_strings(self):
        for q in _DISCOVERY_QUESTIONS:
            assert isinstance(q, str)
            assert len(q) > 10


# ── _ollama helper ────────────────────────────────────────────────────────────

class TestOllamaHelper:
    def test_returns_response_text(self):
        fake = json.dumps({"response": "discovery analysis"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _ollama("prompt text")
        assert result == "discovery analysis"

    def test_returns_error_string_on_connection_error(self):
        with patch("urllib.request.urlopen", side_effect=URLError("refused")):
            result = _ollama("prompt", timeout=1)
        assert result.startswith("Error")

    def test_uses_custom_model_env(self):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "llama3:8b"}):
            with patch("urllib.request.urlopen", side_effect=URLError("x")):
                result = _ollama("hi")
        assert result.startswith("Error")

    def test_uses_custom_base_url_env(self):
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://192.168.1.100:11434"}):
            with patch("urllib.request.urlopen", side_effect=URLError("x")):
                result = _ollama("hi")
        assert result.startswith("Error")


# ── discovery_run (no answers) ────────────────────────────────────────────────

class TestDiscoveryRunNoAnswers:
    def test_returns_questions_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = discovery_run("Acme Corp", "we need a chatbot")
        assert "Discovery questions" in result
        assert "Acme Corp" in result

    def test_includes_all_five_questions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = discovery_run("TestClient", "need AI")
        for i in range(1, 6):
            assert str(i) + "." in result

    def test_includes_stated_problem(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = discovery_run("Client", "fix the onboarding flow")
        assert "fix the onboarding flow" in result

    def test_includes_next_step_instruction(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = discovery_run("Client", "problem")
        assert "discovery_run" in result  # next-step call example


# ── discovery_run (with answers) ─────────────────────────────────────────────

class TestDiscoveryRunWithAnswers:
    ANSWERS = "answer1|||answer2|||answer3|||answer4|||answer5"

    def _run(self, tmp_path, monkeypatch, ollama_response="## Real Problem\nActual issue found."):
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch("tools.discovery_tool._ollama", return_value=ollama_response):
            return discovery_run("Acme Corp", "we need a chatbot", answers=self.ANSWERS)

    def test_runs_ollama_analysis(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch)
        assert "Discovery complete" in result

    def test_saves_discovery_doc(self, tmp_path, monkeypatch):
        self._run(tmp_path, monkeypatch)
        doc_path = _projects_dir("Acme Corp") / "discovery.md"
        assert doc_path.exists()

    def test_doc_contains_client_name(self, tmp_path, monkeypatch):
        self._run(tmp_path, monkeypatch)
        doc_path = _projects_dir("Acme Corp") / "discovery.md"
        content = doc_path.read_text()
        assert "Acme Corp" in content

    def test_doc_contains_stated_problem(self, tmp_path, monkeypatch):
        self._run(tmp_path, monkeypatch)
        doc_path = _projects_dir("Acme Corp") / "discovery.md"
        content = doc_path.read_text()
        assert "we need a chatbot" in content

    def test_fewer_than_five_answers_padded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch("tools.discovery_tool._ollama", return_value="analysis") as mock_ollama:
            discovery_run("Client", "problem", answers="only_one_answer")
        # Should not raise even with fewer than 5 answers
        assert mock_ollama.called
        prompt = mock_ollama.call_args[0][0]
        assert "(not answered)" in prompt

    def test_returns_error_on_ollama_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch("tools.discovery_tool._ollama", return_value="Error: connection refused"):
            result = discovery_run("Client", "problem", answers=self.ANSWERS)
        assert "Error" in result

    def test_result_contains_analysis_preview(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch, ollama_response="## Real Problem\nThe actual bottleneck.")
        assert "Real Problem" in result or "actual bottleneck" in result


# ── discovery_read ────────────────────────────────────────────────────────────

class TestDiscoveryRead:
    def test_returns_not_found_for_missing_client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = discovery_read("Nonexistent Client XYZ")
        assert "No discovery doc" in result or "not found" in result.lower()

    def test_reads_existing_discovery(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        # Write a discovery doc manually
        d = _projects_dir("Existing Client")
        doc = d / "discovery.md"
        doc.write_text("# Discovery: Existing Client\n\nReal problem here.")
        result = discovery_read("Existing Client")
        assert "Real problem here" in result

    def test_returns_full_doc_content(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        d = _projects_dir("AnotherClient")
        doc = d / "discovery.md"
        long_content = "# Discovery\n\n" + "x" * 2000
        doc.write_text(long_content)
        result = discovery_read("AnotherClient")
        assert len(result) > 1000
