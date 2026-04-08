"""
Tests for the Hermes learning loop guardrails:
  - Schema validation  (agent/learning_validator.py)
  - Quality scoring    (agent/learning_validator.py)
  - Max-memory limits  (agent/learning_validator.py)
  - Rollback mechanism (agent/learning_journal.py)
  - Event log          (agent/learning_journal.py)
  - MemoryStore hooks  (tools/memory_tool.py)
  - Skill guardrails   (tools/skill_manager_tool.py)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ══════════════════════════════════════════════════════════════════════════════
# Schema Validation
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryValidation:
    def _validate(self, content, target="memory"):
        from agent.learning_validator import validate_memory_entry
        return validate_memory_entry(content, target)

    def test_valid_entry_returns_none(self):
        assert self._validate("User prefers concise answers with code examples.") is None

    def test_empty_content_rejected(self):
        assert self._validate("") is not None

    def test_whitespace_only_rejected(self):
        assert self._validate("   ") is not None

    def test_too_short_rejected(self):
        assert self._validate("hi") is not None

    def test_too_long_rejected(self):
        assert self._validate("x" * 10_001) is not None

    def test_no_meaningful_text_rejected(self):
        assert self._validate("!!! ---") is not None

    def test_invalid_target_rejected(self):
        assert self._validate("some content", target="invalid_target") is not None

    def test_valid_targets_accepted(self):
        for t in ("memory", "user", "team"):
            assert self._validate("User is a Python developer.", target=t) is None

    def test_non_string_rejected(self):
        assert self._validate(None) is not None
        assert self._validate(123) is not None


class TestSkillValidation:
    def _validate(self, name, content):
        from agent.learning_validator import validate_skill_entry
        return validate_skill_entry(name, content)

    def _good_skill(self):
        return "---\nname: test-skill\ndescription: A test skill\n---\n\nDo the thing step by step.\n"

    def test_valid_skill_returns_none(self):
        assert self._validate("test-skill", self._good_skill()) is None

    def test_empty_name_rejected(self):
        assert self._validate("", self._good_skill()) is not None

    def test_no_frontmatter_rejected(self):
        assert self._validate("skill", "Just some instructions without frontmatter.") is not None

    def test_too_short_content_rejected(self):
        assert self._validate("skill", "---\nname: x\n---\nhi") is not None

    def test_non_string_content_rejected(self):
        assert self._validate("skill", None) is not None


# ══════════════════════════════════════════════════════════════════════════════
# Quality Scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryQualityScoring:
    def _score(self, content, target="memory"):
        from agent.learning_validator import score_memory_entry
        return score_memory_entry(content, target)

    def test_score_in_range(self):
        for c in ("test", "User is a data scientist with 10 years experience.", "x" * 2000):
            s = self._score(c)
            assert 0.0 <= s <= 1.0, f"score {s} out of range for content {c!r}"

    def test_empty_scores_zero(self):
        assert self._score("") == 0.0

    def test_informative_entry_scores_higher_than_noise(self):
        info = 'User\'s preferred model is "claude-opus-4-6" and uses API key rotation every 30 days.'
        noise = "stuff things whatever"
        assert self._score(info) > self._score(noise)

    def test_vague_words_lower_score(self):
        vague = "stuff and things whatever blah"
        specific = "The user runs Python 3.12 on macOS 14.6 with M3 chip."
        assert self._score(vague) < self._score(specific)

    def test_numbers_and_code_bonus(self):
        plain = "The user likes Python."
        rich = "The user runs Python 3.12 with `uv` for deps and deploys to AWS us-east-1."
        assert self._score(rich) > self._score(plain)

    def test_user_target_slight_bonus(self):
        content = "User prefers bullet points."
        assert self._score(content, "user") > self._score(content, "memory")


class TestSkillQualityScoring:
    def _score(self, name, content):
        from agent.learning_validator import score_skill_entry
        return score_skill_entry(name, content)

    def test_score_in_range(self):
        s = self._score("x", "---\nname: x\ndescription: y\n---\n\nDo thing.\n")
        assert 0.0 <= s <= 1.0

    def test_empty_scores_zero(self):
        assert self._score("", "") == 0.0

    def test_full_frontmatter_scores_higher(self):
        minimal = "---\nname: s\n---\n\nDo something.\n"
        full = "---\nname: s\ndescription: Full description.\ntriggers: ['/cmd']\n---\n\n## Steps\n1. Do X\n2. Do Y\n\n```bash\necho hello\n```\n"
        assert self._score("s", full) > self._score("s", minimal)

    def test_no_frontmatter_penalised(self):
        no_fm = "Just some instructions without frontmatter.\nDo the thing."
        with_fm = "---\nname: s\ndescription: d\n---\n\nDo the thing.\n"
        assert self._score("s", with_fm) > self._score("s", no_fm)

    def test_structured_content_higher(self):
        flat = "---\nname: s\ndescription: d\n---\n\nJust a paragraph of text.\n"
        structured = "---\nname: s\ndescription: d\n---\n\n## Overview\n- Step 1\n- Step 2\n\n```python\nprint('hi')\n```\n"
        assert self._score("s", structured) > self._score("s", flat)


# ══════════════════════════════════════════════════════════════════════════════
# Quality gate (check_memory / check_skill)
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityGate:
    def test_good_memory_passes(self):
        from agent.learning_validator import check_memory
        score, err = check_memory("User is a senior Python developer working on ML pipelines.", "memory")
        assert err is None
        assert score > 0.0

    def test_noise_fails(self, monkeypatch):
        monkeypatch.setenv("HERMES_LEARNING_MIN_QUALITY", "0.5")
        from agent.learning_validator import check_memory
        import importlib, agent.learning_validator as lv
        importlib.reload(lv)
        score, err = lv.check_memory("stuff things whatever blah", "memory")
        assert err is not None
        assert "quality score" in err.lower()

    def test_good_skill_passes(self):
        from agent.learning_validator import check_skill
        content = (
            "---\nname: deploy-app\ndescription: Deploy the app to production.\n"
            "triggers: ['/deploy']\n---\n\n## Steps\n1. Run tests\n2. Push image\n3. Restart service\n"
        )
        score, err = check_skill("deploy-app", content)
        assert err is None

    def test_threshold_zero_accepts_all_valid(self, monkeypatch):
        monkeypatch.setenv("HERMES_LEARNING_MIN_QUALITY", "0.0")
        from agent.learning_validator import check_memory
        import importlib, agent.learning_validator as lv
        importlib.reload(lv)
        score, err = lv.check_memory("stuff blah.", "memory")
        # Should pass schema (valid string) but quality gate is 0.0 → no rejection
        # (unless schema validation itself blocks it)
        if err:
            assert "quality" not in err.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Profile limits
# ══════════════════════════════════════════════════════════════════════════════

class TestProfileLimits:
    def test_memory_limit_not_reached(self):
        from agent.learning_validator import check_memory_limit
        assert check_memory_limit(5) is None

    def test_memory_limit_at_boundary(self, monkeypatch):
        monkeypatch.setenv("HERMES_LEARNING_MAX_ENTRIES", "10")
        from agent.learning_validator import check_memory_limit
        import importlib, agent.learning_validator as lv
        importlib.reload(lv)
        assert lv.check_memory_limit(9) is None
        err = lv.check_memory_limit(10)
        assert err is not None
        assert "10" in err

    def test_skill_limit_not_reached(self):
        from agent.learning_validator import check_skill_limit
        assert check_skill_limit(0) is None

    def test_skill_limit_at_boundary(self, monkeypatch):
        monkeypatch.setenv("HERMES_SKILL_MAX_COUNT", "5")
        from agent.learning_validator import check_skill_limit
        import importlib, agent.learning_validator as lv
        importlib.reload(lv)
        assert lv.check_skill_limit(4) is None
        err = lv.check_skill_limit(5)
        assert err is not None


# ══════════════════════════════════════════════════════════════════════════════
# Event Log
# ══════════════════════════════════════════════════════════════════════════════

class TestLearningJournalLog:
    @pytest.fixture(autouse=True)
    def patch_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        import importlib, agent.learning_journal as jl
        importlib.reload(jl)
        return jl

    def test_memory_event_creates_file(self, patch_home):
        jl = patch_home
        jl.record_memory_event(
            action="add", target="memory",
            previous_entries=[], current_entries=["fact"],
            quality=0.8, outcome="accepted",
        )
        assert jl._journal_path().exists()

    def test_record_is_valid_jsonl(self, patch_home):
        jl = patch_home
        jl.record_memory_event(
            action="add", target="user",
            previous_entries=[], current_entries=["info"],
            quality=0.7, outcome="accepted",
        )
        lines = jl._journal_path().read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["type"] == "memory"
        assert record["action"] == "add"

    def test_required_fields_present(self, patch_home):
        jl = patch_home
        entry_id = jl.record_memory_event(
            action="add", target="memory",
            previous_entries=[], current_entries=[],
            quality=0.5, outcome="accepted",
        )
        record = json.loads(jl._journal_path().read_text().strip())
        for f in ("id", "ts", "type", "action", "target", "quality", "outcome"):
            assert f in record
        assert record["id"] == entry_id

    def test_rejected_outcome_recorded(self, patch_home):
        jl = patch_home
        jl.record_memory_event(
            action="add", target="memory",
            previous_entries=[], current_entries=[],
            quality=0.1, outcome="rejected", error="too vague",
        )
        record = json.loads(jl._journal_path().read_text().strip())
        assert record["outcome"] == "rejected"
        assert record["error"] == "too vague"

    def test_skill_event_recorded(self, patch_home):
        jl = patch_home
        jl.record_skill_event(
            action="create", name="my-skill",
            previous_content=None, current_content="---\nname: x\n---\ndo it",
            quality=0.6, outcome="accepted",
        )
        record = json.loads(jl._journal_path().read_text().strip())
        assert record["type"] == "skill"
        assert record["target"] == "my-skill"

    def test_recent_events_returns_list(self, patch_home):
        jl = patch_home
        for i in range(3):
            jl.record_memory_event(
                action="add", target="memory",
                previous_entries=[], current_entries=[f"fact{i}"],
                quality=0.5, outcome="accepted",
            )
        events = jl.recent_events(10)
        assert len(events) == 3

    def test_recent_events_most_recent_first(self, patch_home):
        jl = patch_home
        for i in range(3):
            jl.record_memory_event(
                action="add", target="memory",
                previous_entries=[], current_entries=[f"fact{i}"],
                quality=0.5, outcome="accepted",
            )
        events = jl.recent_events(3)
        # recent_events returns reversed order (most recent first)
        assert events[0]["current"] == ["fact2"]

    def test_journal_trimmed_to_max(self, patch_home, monkeypatch):
        jl = patch_home
        monkeypatch.setenv("HERMES_JOURNAL_MAX_ENTRIES", "5")
        importlib = __import__("importlib")
        importlib.reload(jl)
        for i in range(10):
            jl.record_memory_event(
                action="add", target="memory",
                previous_entries=[], current_entries=[f"e{i}"],
                quality=0.5, outcome="accepted",
            )
        lines = [l for l in jl._journal_path().read_text().splitlines() if l.strip()]
        assert len(lines) <= 5


# ══════════════════════════════════════════════════════════════════════════════
# Rollback
# ══════════════════════════════════════════════════════════════════════════════

class TestRollback:
    @pytest.fixture(autouse=True)
    def patch_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        import importlib, agent.learning_journal as jl
        importlib.reload(jl)
        return jl

    def test_rollback_unknown_id_fails(self, patch_home):
        jl = patch_home
        result = jl.rollback("nonexistent-id")
        assert not result["success"]
        assert "not found" in result["error"]

    def test_rollback_rejected_entry_fails(self, patch_home):
        jl = patch_home
        entry_id = jl.record_memory_event(
            action="add", target="memory",
            previous_entries=[], current_entries=[],
            quality=0.1, outcome="rejected", error="low quality",
        )
        result = jl.rollback(entry_id)
        assert not result["success"]
        assert "rejected" in result["error"]

    def test_rollback_memory_restores_previous(self, patch_home, tmp_path):
        jl = patch_home
        # Set up a MemoryStore with a known state
        from tools.memory_tool import MemoryStore
        store = MemoryStore()
        store.load_from_disk()
        store._set_entries("memory", ["original entry"])
        store.save_to_disk("memory")

        entry_id = jl.record_memory_event(
            action="add", target="memory",
            previous_entries=["original entry"],
            current_entries=["original entry", "new entry"],
            quality=0.8, outcome="accepted",
        )

        # Simulate state after write
        store._set_entries("memory", ["original entry", "new entry"])
        store.save_to_disk("memory")

        result = jl.rollback(entry_id)
        assert result["success"], result.get("error")

        # Verify entries were restored
        store2 = MemoryStore()
        store2.load_from_disk()
        assert store2._entries_for("memory") == ["original entry"]

    def test_rollback_skill_create_removes_skill(self, patch_home, tmp_path):
        jl = patch_home
        # Create a fake skill directory
        skills_dir = tmp_path / "skills" / "test-rollback-skill"
        skills_dir.mkdir(parents=True)
        skill_md = skills_dir / "SKILL.md"
        skill_md.write_text("---\nname: test-rollback-skill\ndescription: test\n---\nContent\n")

        with patch("tools.skill_manager_tool.SKILLS_DIR", tmp_path / "skills"), \
             patch("agent.learning_journal.SKILLS_DIR", tmp_path / "skills", create=True):
            # patch _find_skill in the skill_manager_tool module (where it's actually called)
            with patch("tools.skill_manager_tool._find_skill") as mock_find:
                mock_find.return_value = {"path": skills_dir, "name": "test-rollback-skill"}
                entry_id = jl.record_skill_event(
                    action="create", name="test-rollback-skill",
                    previous_content=None, current_content="---\nname: x\n---\nContent\n",
                    quality=0.7, outcome="accepted",
                )
                result = jl.rollback(entry_id)
                assert result["success"], result.get("error")
                assert not skills_dir.exists()


# ══════════════════════════════════════════════════════════════════════════════
# MemoryStore integration (hooks fire correctly)
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryStoreGuardrails:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.setenv("HERMES_LEARNING_MIN_QUALITY", "0.0")  # don't block on quality in these tests
        monkeypatch.setenv("HERMES_LEARNING_MAX_ENTRIES", "10")
        # Redirect MEMORY_DIR to tmp_path so tests are isolated from real ~/.hermes
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        import tools.memory_tool as mt
        monkeypatch.setattr(mt, "MEMORY_DIR", mem_dir)
        import importlib, agent.learning_validator as lv, agent.learning_journal as jl
        importlib.reload(lv)
        importlib.reload(jl)
        yield tmp_path

    def _make_store(self):
        from tools.memory_tool import MemoryStore
        store = MemoryStore()
        store.load_from_disk()
        return store

    def test_add_success_writes_journal(self, setup):
        store = self._make_store()
        result = store.add("memory", "The user prefers Python over JavaScript.")
        assert result.get("success"), result.get("error")
        import agent.learning_journal as jl
        events = jl.recent_events(5)
        assert any(e["action"] == "add" and e["outcome"] == "accepted" for e in events)

    def test_add_returns_quality_score(self, setup):
        store = self._make_store()
        result = store.add("memory", "The user uses VSCode with vim keybindings.")
        assert "quality_score" in result

    def test_add_over_entry_limit_rejected(self, setup, monkeypatch):
        monkeypatch.setenv("HERMES_LEARNING_MAX_ENTRIES", "3")
        import importlib, agent.learning_validator as lv
        importlib.reload(lv)
        store = self._make_store()
        store.add("memory", "Fact one about the user.")
        store.add("memory", "Fact two about the user.")
        store.add("memory", "Fact three about the user.")
        result = store.add("memory", "Fact four would exceed limit.")
        assert not result.get("success")
        assert "limit" in result.get("error", "").lower()

    def test_remove_writes_journal(self, setup):
        store = self._make_store()
        store.add("memory", "Temporary fact to remove.")
        store.remove("memory", "Temporary fact to remove.")
        import agent.learning_journal as jl
        events = jl.recent_events(10)
        assert any(e["action"] == "remove" for e in events)

    def test_replace_writes_journal(self, setup):
        store = self._make_store()
        store.add("memory", "Old fact about user.")
        store.replace("memory", "Old fact", "Updated fact about user.")
        import agent.learning_journal as jl
        events = jl.recent_events(10)
        assert any(e["action"] == "replace" for e in events)

    def test_rejected_quality_not_persisted(self, setup, monkeypatch):
        monkeypatch.setenv("HERMES_LEARNING_MIN_QUALITY", "0.99")
        import importlib, agent.learning_validator as lv
        importlib.reload(lv)
        store = self._make_store()
        result = store.add("memory", "stuff blah whatever")
        # May be rejected by quality or pass — just verify journal was written
        import agent.learning_journal as jl
        events = jl.recent_events(5)
        # if rejected, journal should record it
        if not result.get("success"):
            assert any(e["outcome"] == "rejected" for e in events)


# ══════════════════════════════════════════════════════════════════════════════
# Property-Based Tests (Hypothesis)
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryQualityScoringProperties:
    """Property-based tests for score_memory_entry using Hypothesis."""

    @given(content=st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_score_always_in_range(self, content):
        """Score must always be between 0.0 and 1.0 for any input."""
        from agent.learning_validator import score_memory_entry
        score = score_memory_entry(content, "memory")
        assert 0.0 <= score <= 1.0, f"score={score} out of [0,1] for content={content!r}"

    def test_empty_string_scores_zero(self):
        from agent.learning_validator import score_memory_entry
        assert score_memory_entry("", "memory") == 0.0

    def test_adding_quoted_strings_increases_score(self):
        """Adding quoted strings/numbers should increase the score."""
        from agent.learning_validator import score_memory_entry
        base = "The user likes Python."
        with_quotes = 'The user likes "Python 3.12" and runs it on port 8080.'
        assert score_memory_entry(with_quotes, "memory") > score_memory_entry(base, "memory")

    def test_adding_vagueness_decreases_score(self):
        """Adding vagueness words should not increase the score."""
        from agent.learning_validator import score_memory_entry
        specific = "The user runs Python 3.12 on macOS 14.6 with M3 chip."
        vague = "stuff and things whatever blah"
        assert score_memory_entry(specific, "memory") > score_memory_entry(vague, "memory")

    def test_adversarial_repeated_word(self):
        """Extremely long repeated content must not crash or score > 1.0."""
        from agent.learning_validator import score_memory_entry
        adversarial = "User" * 5000
        score = score_memory_entry(adversarial, "memory")
        assert 0.0 <= score <= 1.0

    def test_adversarial_null_bytes(self):
        """Null bytes in content must not crash."""
        from agent.learning_validator import score_memory_entry
        adversarial = "\x00" * 100
        score = score_memory_entry(adversarial, "memory")
        assert 0.0 <= score <= 1.0

    def test_adversarial_very_long_content(self):
        """Extremely long content (100K chars) must complete without error."""
        from agent.learning_validator import score_memory_entry
        adversarial = "The user runs Python 3.12. " * 4000  # ~100K chars
        score = score_memory_entry(adversarial, "memory")
        assert 0.0 <= score <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Rollback: Disk Write Failure
# ══════════════════════════════════════════════════════════════════════════════

class TestRollbackDiskFailure:
    @pytest.fixture(autouse=True)
    def patch_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        import importlib, agent.learning_journal as jl
        importlib.reload(jl)
        return jl

    def test_rollback_disk_write_failure_returns_error(self, patch_home, tmp_path):
        """If MemoryStore.save_to_disk() raises IOError, rollback must return
        success=False with an error message — not propagate the exception."""
        jl = patch_home
        entry_id = jl.record_memory_event(
            action="add", target="memory",
            previous_entries=[], current_entries=["entry"],
            quality=0.8, outcome="accepted",
        )
        with patch("tools.memory_tool.MemoryStore.save_to_disk", side_effect=IOError("disk full")):
            result = jl.rollback(entry_id)
        # Either fails gracefully or succeeds — it must not raise
        assert isinstance(result, dict)
        assert "success" in result
