"""Tests for agent/reverse_engineer.py — codebase scanner and context builder."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a fake repo at tmp_path with the given file contents."""
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# build_tree
# ---------------------------------------------------------------------------

class TestBuildTree:
    def test_includes_root_name(self, tmp_path):
        from agent.reverse_engineer import build_tree
        result = build_tree(tmp_path)
        assert tmp_path.name in result

    def test_lists_files(self, tmp_path):
        from agent.reverse_engineer import build_tree
        (tmp_path / "main.py").write_text("# main")
        result = build_tree(tmp_path)
        assert "main.py" in result

    def test_lists_subdirectories(self, tmp_path):
        from agent.reverse_engineer import build_tree
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("# app")
        result = build_tree(tmp_path)
        assert "src/" in result
        assert "app.py" in result

    def test_skips_node_modules(self, tmp_path):
        from agent.reverse_engineer import build_tree
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "some-lib").mkdir(parents=True)
        (nm / "some-lib" / "index.js").write_text("// lib")
        (tmp_path / "main.py").write_text("# entry")
        result = build_tree(tmp_path)
        # node_modules dir itself should not be listed (even if tmp dir name contains the string)
        lines = result.splitlines()
        # Skip first line (root name) and check no line shows node_modules as a child entry
        child_lines = lines[1:]  # skip root
        assert not any(line.strip().endswith("node_modules/") for line in child_lines)

    def test_skips_pycache(self, tmp_path):
        from agent.reverse_engineer import build_tree
        pc = tmp_path / "__pycache__"
        pc.mkdir()
        (pc / "something.pyc").write_text("")
        result = build_tree(tmp_path)
        assert "__pycache__" not in result

    def test_skips_venv(self, tmp_path):
        from agent.reverse_engineer import build_tree
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "pyvenv.cfg").write_text("")
        result = build_tree(tmp_path)
        assert ".venv" not in result

    def test_depth_limit_respected(self, tmp_path):
        from agent.reverse_engineer import build_tree
        deep = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("")
        result = build_tree(tmp_path, max_depth=2)
        # At max_depth=2 we should see depth limit hint
        assert "depth limit" in result

    def test_returns_string(self, tmp_path):
        from agent.reverse_engineer import build_tree
        assert isinstance(build_tree(tmp_path), str)


# ---------------------------------------------------------------------------
# read_key_files
# ---------------------------------------------------------------------------

class TestReadKeyFiles:
    def test_reads_readme(self, tmp_path):
        from agent.reverse_engineer import read_key_files
        (tmp_path / "README.md").write_text("# My Project\n\nDoes stuff.")
        result = read_key_files(tmp_path)
        assert "My Project" in result
        assert "README.md" in result

    def test_reads_package_json(self, tmp_path):
        from agent.reverse_engineer import read_key_files
        (tmp_path / "package.json").write_text('{"name": "my-app", "version": "1.0.0"}')
        result = read_key_files(tmp_path)
        assert "my-app" in result

    def test_reads_requirements_txt(self, tmp_path):
        from agent.reverse_engineer import read_key_files
        (tmp_path / "requirements.txt").write_text("flask==2.0.0\nrequests>=2.28")
        result = read_key_files(tmp_path)
        assert "flask" in result

    def test_skips_missing_files(self, tmp_path):
        from agent.reverse_engineer import read_key_files
        # No files at all
        result = read_key_files(tmp_path)
        assert "no standard config" in result.lower() or result == "(no standard config/readme files found)"

    def test_truncates_large_file(self, tmp_path):
        from agent.reverse_engineer import read_key_files, _FILE_MAX_CHARS
        big_content = "x" * (_FILE_MAX_CHARS + 1000)
        (tmp_path / "README.md").write_text(big_content)
        result = read_key_files(tmp_path)
        assert "truncated" in result

    def test_returns_string(self, tmp_path):
        from agent.reverse_engineer import read_key_files
        assert isinstance(read_key_files(tmp_path), str)

    def test_multiple_files_combined(self, tmp_path):
        from agent.reverse_engineer import read_key_files
        (tmp_path / "README.md").write_text("# Readme")
        (tmp_path / "requirements.txt").write_text("pytest")
        result = read_key_files(tmp_path)
        assert "README.md" in result
        assert "requirements.txt" in result


# ---------------------------------------------------------------------------
# detect_entry_points
# ---------------------------------------------------------------------------

class TestDetectEntryPoints:
    def test_finds_main_py(self, tmp_path):
        from agent.reverse_engineer import detect_entry_points
        (tmp_path / "main.py").write_text("def main(): pass\n\nif __name__ == '__main__': main()")
        result = detect_entry_points(tmp_path)
        assert any("main.py" in r for r in result)

    def test_finds_app_py(self, tmp_path):
        from agent.reverse_engineer import detect_entry_points
        (tmp_path / "app.py").write_text("from flask import Flask\napp = Flask(__name__)")
        result = detect_entry_points(tmp_path)
        assert any("app.py" in r for r in result)

    def test_finds_index_ts(self, tmp_path):
        from agent.reverse_engineer import detect_entry_points
        (tmp_path / "index.ts").write_text("export default function main() {}")
        result = detect_entry_points(tmp_path)
        assert any("index.ts" in r for r in result)

    def test_returns_empty_when_none_found(self, tmp_path):
        from agent.reverse_engineer import detect_entry_points
        result = detect_entry_points(tmp_path)
        assert result == []

    def test_snippet_truncated_to_1500_chars(self, tmp_path):
        from agent.reverse_engineer import detect_entry_points
        (tmp_path / "main.py").write_text("x = 1\n" * 500)
        result = detect_entry_points(tmp_path)
        # The entry in the result list should be under 1500 + header chars
        assert result  # found it
        assert len(result[0]) < 2500  # not the full file

    def test_reads_src_subdirectory(self, tmp_path):
        from agent.reverse_engineer import detect_entry_points
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# src main")
        result = detect_entry_points(tmp_path)
        assert any("src/main.py" in r for r in result)


# ---------------------------------------------------------------------------
# detect_tech_stack
# ---------------------------------------------------------------------------

class TestDetectTechStack:
    def test_detects_python_from_files(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        (tmp_path / "main.py").write_text("print('hello')")
        result = detect_tech_stack(tmp_path)
        assert "python" in result

    def test_detects_typescript_from_files(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        (tmp_path / "index.ts").write_text("const x: number = 1;")
        result = detect_tech_stack(tmp_path)
        assert "typescript" in result

    def test_detects_docker_from_dockerfile(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        (tmp_path / "Dockerfile").write_text("FROM python:3.11")
        result = detect_tech_stack(tmp_path)
        assert "docker" in result

    def test_detects_nextjs_from_config(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        (tmp_path / "next.config.js").write_text("module.exports = {}")
        result = detect_tech_stack(tmp_path)
        assert "nextjs" in result

    def test_detects_flask_from_requirements(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        (tmp_path / "main.py").write_text("from flask import Flask")
        (tmp_path / "requirements.txt").write_text("flask==2.0.0\n")
        result = detect_tech_stack(tmp_path)
        assert "python" in result
        assert "flask" in result

    def test_detects_redis_from_requirements(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        (tmp_path / "requirements.txt").write_text("redis==4.5.0\n")
        result = detect_tech_stack(tmp_path)
        assert "redis" in result

    def test_returns_list(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        assert isinstance(detect_tech_stack(tmp_path), list)

    def test_caps_at_ten(self, tmp_path):
        from agent.reverse_engineer import detect_tech_stack
        # Make lots of signals
        for ext in [".py", ".ts", ".go", ".rs", ".java"]:
            (tmp_path / f"main{ext}").write_text("")
        (tmp_path / "Dockerfile").write_text("FROM scratch")
        (tmp_path / "next.config.js").write_text("")
        (tmp_path / "requirements.txt").write_text("flask\nredis\npostgresql\n")
        result = detect_tech_stack(tmp_path)
        assert len(result) <= 10


# ---------------------------------------------------------------------------
# extract_dependencies
# ---------------------------------------------------------------------------

class TestExtractDependencies:
    def test_reads_requirements_txt(self, tmp_path):
        from agent.reverse_engineer import extract_dependencies
        (tmp_path / "requirements.txt").write_text("flask==2.0.0\nrequests>=2.28\n# comment\n\n")
        result = extract_dependencies(tmp_path)
        assert "python" in result
        assert "flask==2.0.0" in result["python"]
        assert "requests>=2.28" in result["python"]

    def test_skips_comments_in_requirements(self, tmp_path):
        from agent.reverse_engineer import extract_dependencies
        (tmp_path / "requirements.txt").write_text("# this is a comment\nflask\n")
        result = extract_dependencies(tmp_path)
        assert all(not d.startswith("#") for d in result.get("python", []))

    def test_reads_package_json_dependencies(self, tmp_path):
        from agent.reverse_engineer import extract_dependencies
        pkg = {"dependencies": {"express": "^4.18", "lodash": "^4.17"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = extract_dependencies(tmp_path)
        assert "node_runtime" in result
        assert "express" in result["node_runtime"]

    def test_reads_package_json_dev_dependencies(self, tmp_path):
        from agent.reverse_engineer import extract_dependencies
        pkg = {"devDependencies": {"jest": "^29", "typescript": "^5"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = extract_dependencies(tmp_path)
        assert "node_dev" in result
        assert "jest" in result["node_dev"]

    def test_returns_empty_dict_when_no_manifests(self, tmp_path):
        from agent.reverse_engineer import extract_dependencies
        result = extract_dependencies(tmp_path)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_returns_dict(self, tmp_path):
        from agent.reverse_engineer import extract_dependencies
        assert isinstance(extract_dependencies(tmp_path), dict)


# ---------------------------------------------------------------------------
# get_repo_name
# ---------------------------------------------------------------------------

class TestGetRepoName:
    def test_falls_back_to_dirname(self, tmp_path):
        from agent.reverse_engineer import get_repo_name
        result = get_repo_name(tmp_path)
        assert result == tmp_path.name

    def test_returns_string(self, tmp_path):
        from agent.reverse_engineer import get_repo_name
        assert isinstance(get_repo_name(tmp_path), str)


# ---------------------------------------------------------------------------
# clone_if_url
# ---------------------------------------------------------------------------

class TestCloneIfUrl:
    def test_returns_expanded_local_path(self, tmp_path):
        from agent.reverse_engineer import clone_if_url
        result = clone_if_url(str(tmp_path), tmp_path)
        assert result == tmp_path

    def test_expands_tilde(self, tmp_path):
        from agent.reverse_engineer import clone_if_url
        # Use home directory path — should not raise
        home = Path.home()
        result = clone_if_url("~", tmp_path)
        assert result == home

    def test_github_url_triggers_clone(self, tmp_path):
        from agent.reverse_engineer import clone_if_url
        import subprocess as _sp
        with patch("agent.reverse_engineer.subprocess") as mock_sp:
            mock_sp.run.return_value = None
            # Simulate dest already exists
            dest = tmp_path / "my-repo"
            dest.mkdir()
            result = clone_if_url("https://github.com/owner/my-repo", tmp_path)
            assert result == dest

    def test_non_github_url_treated_as_path(self, tmp_path):
        from agent.reverse_engineer import clone_if_url
        result = clone_if_url(str(tmp_path), tmp_path / "clones")
        assert result == tmp_path


# ---------------------------------------------------------------------------
# build_revengineer_context (integration)
# ---------------------------------------------------------------------------

class TestBuildRevengineeerContext:
    def test_returns_tuple_of_path_and_string(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        (tmp_path / "README.md").write_text("# Hello")
        (tmp_path / "main.py").write_text("print('hi')")
        root, context = build_revengineer_context(str(tmp_path))
        assert isinstance(root, Path)
        assert isinstance(context, str)

    def test_context_contains_codebase_scan_header(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        (tmp_path / "main.py").write_text("# entry")
        _, context = build_revengineer_context(str(tmp_path))
        assert "Codebase Scan" in context

    def test_context_contains_directory_structure(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        (tmp_path / "main.py").write_text("# entry")
        _, context = build_revengineer_context(str(tmp_path))
        assert "Directory Structure" in context

    def test_context_contains_detected_stack(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        (tmp_path / "main.py").write_text("# entry")
        (tmp_path / "requirements.txt").write_text("flask\n")
        _, context = build_revengineer_context(str(tmp_path))
        assert "python" in context.lower() or "Detected stack" in context

    def test_raises_for_nonexistent_path(self):
        from agent.reverse_engineer import build_revengineer_context
        with pytest.raises(FileNotFoundError):
            build_revengineer_context("/tmp/this_path_does_not_exist_xyz_123")

    def test_raises_for_file_not_directory(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        f = tmp_path / "file.py"
        f.write_text("# not a dir")
        with pytest.raises(NotADirectoryError):
            build_revengineer_context(str(f))

    def test_context_contains_repo_name(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        _, context = build_revengineer_context(str(tmp_path))
        assert tmp_path.name in context

    def test_context_contains_entry_points_section(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        (tmp_path / "main.py").write_text("def main(): pass")
        _, context = build_revengineer_context(str(tmp_path))
        assert "Entry Points" in context

    def test_context_contains_dependencies_section(self, tmp_path):
        from agent.reverse_engineer import build_revengineer_context
        _, context = build_revengineer_context(str(tmp_path))
        assert "Dependencies" in context
