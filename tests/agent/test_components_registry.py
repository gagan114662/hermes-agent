"""Unit tests for agent.components_registry — skill provenance tracking.

All filesystem I/O uses tmp_path; no real ~/.hermes writes.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _patch_registry_path(tmp_path):
    from agent import components_registry as cr
    return patch.object(cr, "_registry_path", return_value=tmp_path / "components.jsonl")


# ---------------------------------------------------------------------------
# register_skill / get_provenance
# ---------------------------------------------------------------------------

class TestRegisterSkill:
    def test_creates_jsonl_file(self, tmp_path):
        from agent import components_registry as cr
        skill_md = tmp_path / "my-skill" / "SKILL.md"
        skill_md.parent.mkdir()
        skill_md.write_text("---\nname: my-skill\n---\n# Test", encoding="utf-8")
        with _patch_registry_path(tmp_path):
            cr.register_skill("my-skill", str(skill_md))
        assert (tmp_path / "components.jsonl").exists()

    def test_provenance_fields(self, tmp_path):
        from agent import components_registry as cr
        skill_md = tmp_path / "s" / "SKILL.md"
        skill_md.parent.mkdir()
        skill_md.write_text("hello", encoding="utf-8")
        with _patch_registry_path(tmp_path):
            cr.register_skill("s", str(skill_md), source="community",
                               origin="https://example.com/s.md",
                               version="1.2.0", author="Alice",
                               description="Does stuff")
            rec = cr.get_provenance("s")
        assert rec["id"] == "s"
        assert rec["source"] == "community"
        assert rec["origin"] == "https://example.com/s.md"
        assert rec["version"] == "1.2.0"
        assert rec["author"] == "Alice"
        assert rec["description"] == "Does stuff"

    def test_checksum_stored(self, tmp_path):
        from agent import components_registry as cr
        import hashlib
        content = b"skill content"
        skill_md = tmp_path / "x" / "SKILL.md"
        skill_md.parent.mkdir()
        skill_md.write_bytes(content)
        with _patch_registry_path(tmp_path):
            cr.register_skill("x", str(skill_md))
            rec = cr.get_provenance("x")
        expected = hashlib.sha256(content).hexdigest()
        assert rec["checksum"] == expected

    def test_update_overwrites_provenance(self, tmp_path):
        from agent import components_registry as cr
        skill_md = tmp_path / "upd" / "SKILL.md"
        skill_md.parent.mkdir()
        skill_md.write_text("v1", encoding="utf-8")
        with _patch_registry_path(tmp_path):
            cr.register_skill("upd", str(skill_md), version="1.0.0")
            cr.register_skill("upd", str(skill_md), version="2.0.0")
            rec = cr.get_provenance("upd")
        assert rec["version"] == "2.0.0"

    def test_get_provenance_missing_returns_none(self, tmp_path):
        from agent import components_registry as cr
        with _patch_registry_path(tmp_path):
            assert cr.get_provenance("nonexistent") is None


# ---------------------------------------------------------------------------
# list_installed
# ---------------------------------------------------------------------------

class TestListInstalled:
    def test_empty_when_no_registry(self, tmp_path):
        from agent import components_registry as cr
        with _patch_registry_path(tmp_path):
            assert cr.list_installed() == []

    def test_returns_registered_skills(self, tmp_path):
        from agent import components_registry as cr
        for name in ("skill-a", "skill-b"):
            md = tmp_path / name / "SKILL.md"
            md.parent.mkdir()
            md.write_text("x", encoding="utf-8")
            with _patch_registry_path(tmp_path):
                cr.register_skill(name, str(md))
        with _patch_registry_path(tmp_path):
            result = cr.list_installed()
        ids = {r["id"] for r in result}
        assert "skill-a" in ids and "skill-b" in ids

    def test_deduplicates_by_id(self, tmp_path):
        from agent import components_registry as cr
        md = tmp_path / "dup" / "SKILL.md"
        md.parent.mkdir()
        md.write_text("x", encoding="utf-8")
        with _patch_registry_path(tmp_path):
            cr.register_skill("dup", str(md), version="1.0")
            cr.register_skill("dup", str(md), version="2.0")
            result = cr.list_installed()
        assert len(result) == 1
        assert result[0]["version"] == "2.0"

    def test_excludes_deleted(self, tmp_path):
        from agent import components_registry as cr
        md = tmp_path / "gone" / "SKILL.md"
        md.parent.mkdir()
        md.write_text("x", encoding="utf-8")
        with _patch_registry_path(tmp_path):
            cr.register_skill("gone", str(md))
            cr.unregister_skill("gone")
            result = cr.list_installed()
        assert result == []


# ---------------------------------------------------------------------------
# unregister_skill
# ---------------------------------------------------------------------------

class TestUnregisterSkill:
    def test_returns_true_for_existing(self, tmp_path):
        from agent import components_registry as cr
        md = tmp_path / "rm" / "SKILL.md"
        md.parent.mkdir(); md.write_text("x", encoding="utf-8")
        with _patch_registry_path(tmp_path):
            cr.register_skill("rm", str(md))
            assert cr.unregister_skill("rm") is True

    def test_returns_false_for_missing(self, tmp_path):
        from agent import components_registry as cr
        with _patch_registry_path(tmp_path):
            assert cr.unregister_skill("does-not-exist") is False

    def test_provenance_none_after_unregister(self, tmp_path):
        from agent import components_registry as cr
        md = tmp_path / "gone2" / "SKILL.md"
        md.parent.mkdir(); md.write_text("x", encoding="utf-8")
        with _patch_registry_path(tmp_path):
            cr.register_skill("gone2", str(md))
            cr.unregister_skill("gone2")
            assert cr.get_provenance("gone2") is None


# ---------------------------------------------------------------------------
# try_auto_register
# ---------------------------------------------------------------------------

class TestTryAutoRegister:
    def test_returns_false_when_skill_missing(self, tmp_path):
        from agent import components_registry as cr
        with _patch_registry_path(tmp_path):
            ok = cr.try_auto_register("no-such-skill", skills_base_dir=str(tmp_path))
        assert ok is False

    def test_returns_true_and_registers(self, tmp_path):
        from agent import components_registry as cr
        skills_base = tmp_path / "skills"
        (skills_base / "my-tool").mkdir(parents=True)
        (skills_base / "my-tool" / "SKILL.md").write_text(
            "---\nauthor: Bob\nversion: 1.0.0\ndescription: Does stuff\n---\n",
            encoding="utf-8"
        )
        with _patch_registry_path(tmp_path):
            ok = cr.try_auto_register("my-tool", skills_base_dir=str(skills_base))
            rec = cr.get_provenance("my-tool")
        assert ok is True
        assert rec["author"] == "Bob"
        assert rec["version"] == "1.0.0"
        assert "Does stuff" in rec["description"]

    def test_parses_frontmatter(self, tmp_path):
        from agent import components_registry as cr
        skills_base = tmp_path / "skills"
        (skills_base / "fm-skill").mkdir(parents=True)
        (skills_base / "fm-skill" / "SKILL.md").write_text(
            '---\nname: FM Skill\nauthor: "Carol"\nversion: "2.1"\ndescription: >-\n  A multi-line\n  description\n---\n',
            encoding="utf-8"
        )
        with _patch_registry_path(tmp_path):
            cr.try_auto_register("fm-skill", skills_base_dir=str(skills_base))
            rec = cr.get_provenance("fm-skill")
        assert rec["author"] == "Carol"
        assert rec["version"] == "2.1"
