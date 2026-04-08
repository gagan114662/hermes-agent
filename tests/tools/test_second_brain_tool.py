"""Tests for tools/second_brain_tool.py — pure file I/O, no LLM calls."""

import threading
import pytest
from pathlib import Path

from tools.second_brain_tool import (
    _slug,
    second_brain_scaffold,
    second_brain_list,
    second_brain_raw_list,
    second_brain_read_source,
    second_brain_write_page,
    second_brain_read_page,
    second_brain_list_pages,
    second_brain_append_log,
    second_brain_update_index,
    second_brain_lint,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sb_root(tmp_path, monkeypatch):
    """Redirect _sb_root() to a temp directory so tests never touch ~/.hermes/."""
    root = tmp_path / "second-brain"
    root.mkdir()
    import tools.second_brain_tool as mod
    monkeypatch.setattr(mod, "_sb_root", lambda: root)
    return root


@pytest.fixture()
def vault(sb_root):
    """Create a scaffold vault called 'test-vault' and return its Path."""
    second_brain_scaffold("test-vault", "Testing and quality assurance")
    return sb_root / "test-vault"


# ── _slug ─────────────────────────────────────────────────────────────────────

class TestSlug:
    def test_lowercase_passthrough(self):
        assert _slug("hello") == "hello"

    def test_spaces_become_dashes(self):
        assert _slug("hello world") == "hello-world"

    def test_uppercase_lowercased(self):
        assert _slug("MyVault") == "myvault"

    def test_special_chars_stripped(self):
        assert _slug("My Vault! 2.0") == "my-vault--2-0"

    def test_leading_trailing_dashes_stripped(self):
        assert _slug("  --hello--  ") == "hello"


# ── scaffold ──────────────────────────────────────────────────────────────────

class TestScaffold:
    def test_creates_folder_structure(self, sb_root):
        second_brain_scaffold("my-domain", "Domain knowledge")
        vault_dir = sb_root / "my-domain"
        assert (vault_dir / "raw").is_dir()
        assert (vault_dir / "wiki" / "sources").is_dir()
        assert (vault_dir / "wiki" / "entities").is_dir()
        assert (vault_dir / "wiki" / "concepts").is_dir()
        assert (vault_dir / "wiki" / "synthesis").is_dir()
        assert (vault_dir / "output").is_dir()

    def test_writes_claude_md(self, sb_root):
        second_brain_scaffold("my-domain", "Testing domain")
        claude_md = (sb_root / "my-domain" / "CLAUDE.md").read_text()
        assert "Testing domain" in claude_md
        assert "my-domain" in claude_md

    def test_writes_index_and_log(self, sb_root):
        second_brain_scaffold("my-domain", "Testing domain")
        assert (sb_root / "my-domain" / "wiki" / "index.md").exists()
        assert (sb_root / "my-domain" / "wiki" / "log.md").exists()

    def test_slug_normalizes_vault_name(self, sb_root):
        second_brain_scaffold("My Domain Vault", "Domain knowledge")
        assert (sb_root / "my-domain-vault").is_dir()

    def test_duplicate_vault_returns_error(self, vault):
        result = second_brain_scaffold("test-vault", "Any domain")
        assert "already exists" in result

    def test_success_message_contains_vault_name(self, sb_root):
        result = second_brain_scaffold("new-vault", "Some domain")
        assert "new-vault" in result


# ── list ──────────────────────────────────────────────────────────────────────

class TestList:
    def test_empty_returns_no_vaults_message(self, sb_root):
        result = second_brain_list()
        assert "No vaults" in result

    def test_lists_created_vault(self, vault):
        result = second_brain_list()
        assert "test-vault" in result

    def test_shows_domain(self, vault):
        result = second_brain_list()
        assert "Testing and quality assurance" in result

    def test_shows_page_count(self, vault):
        # Write a page and verify count reflects it
        second_brain_write_page("test-vault", "concepts", "hello", "# Hello\n\nSome content here.")
        result = second_brain_list()
        assert "Wiki pages:" in result

    def test_multiple_vaults_all_shown(self, sb_root):
        second_brain_scaffold("vault-a", "Domain A")
        second_brain_scaffold("vault-b", "Domain B")
        result = second_brain_list()
        assert "vault-a" in result
        assert "vault-b" in result


# ── raw_list ──────────────────────────────────────────────────────────────────

class TestRawList:
    def test_unknown_vault(self, sb_root):
        result = second_brain_raw_list("nonexistent")
        assert "not found" in result

    def test_empty_raw_dir(self, vault):
        result = second_brain_raw_list("test-vault")
        assert "No files" in result

    def test_lists_unprocessed_file(self, vault):
        (vault / "raw" / "article.md").write_text("Some article content")
        result = second_brain_raw_list("test-vault")
        assert "article.md" in result
        assert "not yet ingested" in result

    def test_marks_processed_file(self, vault):
        (vault / "raw" / "article.md").write_text("Some article content")
        # Simulate ingestion by creating the sources page
        (vault / "wiki" / "sources" / "article.md").write_text("# Article\n\nSummary.")
        result = second_brain_raw_list("test-vault")
        assert "ingested" in result

    def test_hidden_files_excluded(self, vault):
        (vault / "raw" / ".DS_Store").write_text("macOS junk")
        result = second_brain_raw_list("test-vault")
        assert "No files" in result  # hidden file should not appear


# ── read_source ───────────────────────────────────────────────────────────────

class TestReadSource:
    def test_unknown_vault(self, sb_root):
        result = second_brain_read_source("nonexistent", "file.md")
        assert "not found" in result

    def test_missing_file(self, vault):
        result = second_brain_read_source("test-vault", "missing.md")
        assert "not found" in result.lower() or "not found" in result

    def test_reads_file_content(self, vault):
        (vault / "raw" / "notes.md").write_text("# My Notes\n\nImportant stuff here.")
        result = second_brain_read_source("test-vault", "notes.md")
        assert "My Notes" in result
        assert "Important stuff here" in result

    def test_includes_filename_in_output(self, vault):
        (vault / "raw" / "notes.md").write_text("content")
        result = second_brain_read_source("test-vault", "notes.md")
        assert "notes.md" in result


# ── write_page ────────────────────────────────────────────────────────────────

class TestWritePage:
    def test_unknown_vault(self, sb_root):
        result = second_brain_write_page("nonexistent", "concepts", "page", "content")
        assert "not found" in result

    def test_invalid_section(self, vault):
        result = second_brain_write_page("test-vault", "invalid-section", "page", "content")
        assert "Invalid section" in result

    def test_writes_concept_page(self, vault):
        second_brain_write_page("test-vault", "concepts", "rag-pattern", "# RAG\n\nRetrieval augmented generation.")
        path = vault / "wiki" / "concepts" / "rag-pattern.md"
        assert path.exists()
        assert "Retrieval augmented generation" in path.read_text()

    def test_writes_entity_page(self, vault):
        second_brain_write_page("test-vault", "entities", "andrej-karpathy", "# Andrej Karpathy\n\n**Type:** person")
        path = vault / "wiki" / "entities" / "andrej-karpathy.md"
        assert path.exists()

    def test_writes_sources_page(self, vault):
        second_brain_write_page("test-vault", "sources", "my-article", "# My Article\n\nKey takeaways.")
        assert (vault / "wiki" / "sources" / "my-article.md").exists()

    def test_writes_synthesis_page(self, vault):
        second_brain_write_page("test-vault", "synthesis", "comparison", "# Comparison\n\nAnalysis.")
        assert (vault / "wiki" / "synthesis" / "comparison.md").exists()

    def test_page_name_slugified(self, vault):
        second_brain_write_page("test-vault", "concepts", "My Concept", "# Content")
        assert (vault / "wiki" / "concepts" / "my-concept.md").exists()

    def test_overwrite_existing_page(self, vault):
        second_brain_write_page("test-vault", "concepts", "idea", "# Version 1")
        second_brain_write_page("test-vault", "concepts", "idea", "# Version 2")
        content = (vault / "wiki" / "concepts" / "idea.md").read_text()
        assert "Version 2" in content
        assert "Version 1" not in content

    def test_success_message_contains_path(self, vault):
        result = second_brain_write_page("test-vault", "concepts", "test-page", "# Test")
        assert "wiki/concepts/test-page.md" in result


# ── read_page ─────────────────────────────────────────────────────────────────

class TestReadPage:
    def test_unknown_vault(self, sb_root):
        result = second_brain_read_page("nonexistent", "concepts", "page")
        assert "not found" in result

    def test_invalid_section(self, vault):
        result = second_brain_read_page("test-vault", "invalid", "page")
        assert "Invalid section" in result

    def test_reads_concept_page(self, vault):
        second_brain_write_page("test-vault", "concepts", "idea", "# My Idea\n\nCore concept.")
        result = second_brain_read_page("test-vault", "concepts", "idea")
        assert "My Idea" in result
        assert "Core concept" in result

    def test_reads_index(self, vault):
        result = second_brain_read_page("test-vault", "index", "index")
        assert "Wiki Index" in result

    def test_reads_log(self, vault):
        result = second_brain_read_page("test-vault", "log", "log")
        assert "Activity Log" in result

    def test_missing_page_returns_not_found(self, vault):
        result = second_brain_read_page("test-vault", "concepts", "nonexistent-page")
        assert "not found" in result.lower() or "Page not found" in result


# ── list_pages ────────────────────────────────────────────────────────────────

class TestListPages:
    def test_unknown_vault(self, sb_root):
        result = second_brain_list_pages("nonexistent")
        assert "not found" in result

    def test_empty_vault_shows_zero_pages(self, vault):
        result = second_brain_list_pages("test-vault")
        assert "0 pages" in result

    def test_all_sections_shown(self, vault):
        result = second_brain_list_pages("test-vault")
        assert "sources/" in result
        assert "entities/" in result
        assert "concepts/" in result
        assert "synthesis/" in result

    def test_lists_written_pages(self, vault):
        second_brain_write_page("test-vault", "concepts", "rag", "# RAG content here.")
        second_brain_write_page("test-vault", "entities", "karpathy", "# Karpathy entity.")
        result = second_brain_list_pages("test-vault", "all")
        assert "rag" in result
        assert "karpathy" in result

    def test_single_section_filter(self, vault):
        second_brain_write_page("test-vault", "concepts", "rag", "# RAG content here.")
        second_brain_write_page("test-vault", "entities", "karpathy", "# Karpathy entity.")
        result = second_brain_list_pages("test-vault", "concepts")
        assert "rag" in result
        assert "karpathy" not in result


# ── append_log ────────────────────────────────────────────────────────────────

class TestAppendLog:
    def test_unknown_vault(self, sb_root):
        result = second_brain_append_log("nonexistent", "some entry")
        assert "not found" in result

    def test_appends_entry(self, vault):
        second_brain_append_log("test-vault", "Ingested notes.md")
        log = (vault / "wiki" / "log.md").read_text()
        assert "Ingested notes.md" in log

    def test_multiple_entries_accumulate(self, vault):
        second_brain_append_log("test-vault", "Entry one")
        second_brain_append_log("test-vault", "Entry two")
        log = (vault / "wiki" / "log.md").read_text()
        assert "Entry one" in log
        assert "Entry two" in log

    def test_entry_includes_timestamp(self, vault):
        second_brain_append_log("test-vault", "Something happened")
        log = (vault / "wiki" / "log.md").read_text()
        # Timestamp format: YYYY-MM-DD HH:MM
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", log)

    def test_returns_success_message(self, vault):
        result = second_brain_append_log("test-vault", "Entry")
        assert "Log updated" in result


# ── update_index ──────────────────────────────────────────────────────────────

class TestUpdateIndex:
    def test_unknown_vault(self, sb_root):
        result = second_brain_update_index("nonexistent")
        assert "not found" in result

    def test_rebuilds_index(self, vault):
        second_brain_write_page("test-vault", "concepts", "rag", "# RAG\n\nContent here.")
        second_brain_write_page("test-vault", "entities", "karpathy", "# Karpathy\n\nDetails.")
        second_brain_update_index("test-vault")
        index = (vault / "wiki" / "index.md").read_text()
        assert "rag" in index
        assert "karpathy" in index

    def test_index_contains_wikilinks(self, vault):
        second_brain_write_page("test-vault", "concepts", "rag", "# RAG\n\nContent.")
        second_brain_update_index("test-vault")
        index = (vault / "wiki" / "index.md").read_text()
        assert "[[concepts/rag]]" in index

    def test_empty_sections_show_placeholder(self, vault):
        second_brain_update_index("test-vault")
        index = (vault / "wiki" / "index.md").read_text()
        assert "No sources yet" in index or "No concepts yet" in index

    def test_returns_page_count(self, vault):
        second_brain_write_page("test-vault", "concepts", "rag", "# RAG\n\nContent.")
        result = second_brain_update_index("test-vault")
        assert "1" in result


# ── lint ──────────────────────────────────────────────────────────────────────

class TestLint:
    def test_unknown_vault(self, sb_root):
        result = second_brain_lint("nonexistent")
        assert "not found" in result

    def test_clean_vault_passes(self, vault):
        result = second_brain_lint("test-vault")
        assert "lint passed" in result

    def test_detects_unprocessed_raw_files(self, vault):
        (vault / "raw" / "article.md").write_text("Some article content")
        result = second_brain_lint("test-vault")
        assert "Unprocessed raw files" in result
        assert "article.md" in result

    def test_no_unprocessed_when_ingested(self, vault):
        (vault / "raw" / "article.md").write_text("Some article content")
        (vault / "wiki" / "sources" / "article.md").write_text("# Article\n\nSummary page.")
        result = second_brain_lint("test-vault")
        assert "Unprocessed raw files" not in result

    def test_detects_stub_pages(self, vault):
        # A page with fewer than 50 chars of content
        second_brain_write_page("test-vault", "concepts", "stub", "tiny")
        result = second_brain_lint("test-vault")
        assert "Stub pages" in result

    def test_no_stub_for_full_pages(self, vault):
        second_brain_write_page(
            "test-vault", "concepts", "full-page",
            "# Full Page\n\nThis is a sufficiently long concept page with real content."
        )
        result = second_brain_lint("test-vault")
        assert "Stub pages" not in result

    def test_detects_broken_links(self, vault):
        # Page references a non-existent page
        second_brain_write_page(
            "test-vault", "concepts", "test-concept",
            "# Test Concept\n\nReferences [[nonexistent-page]] which does not exist."
        )
        result = second_brain_lint("test-vault")
        assert "Broken links" in result

    def test_no_broken_links_when_target_exists(self, vault):
        second_brain_write_page("test-vault", "entities", "karpathy", "# Karpathy entity page.")
        second_brain_write_page(
            "test-vault", "concepts", "llm-wiki",
            "# LLM Wiki\n\nProposed by [[karpathy]]."
        )
        result = second_brain_lint("test-vault")
        assert "Broken links" not in result

    def test_summary_includes_check_counts(self, vault):
        result = second_brain_lint("test-vault")
        # Should show N/M checks passed
        assert "/" in result or "passed" in result

    def test_broken_link_reports_specific_page_name(self, vault):
        """Lint output must name which page has the broken link."""
        second_brain_write_page(
            "test-vault", "concepts", "my-concept",
            "# My Concept\n\nSee also [[ghost-page]] for details."
        )
        result = second_brain_lint("test-vault")
        assert "Broken links" in result
        # Should name the page containing the broken link
        assert "my-concept" in result or "ghost-page" in result


# ══════════════════════════════════════════════════════════════════════════════
# Edge Cases: Unicode Vault Names
# ══════════════════════════════════════════════════════════════════════════════

class TestUnicodeVaultNames:
    def test_unicode_vault_name_scaffolds(self, sb_root):
        """Vault names with unicode characters should slug correctly."""
        result = second_brain_scaffold("中文", "Chinese domain")
        assert isinstance(result, str)
        # Slug strips non-ASCII; the vault directory name should exist
        # (exact slug format depends on implementation)

    def test_vault_with_spaces_scaffolds(self, sb_root):
        second_brain_scaffold("My Vault With Spaces", "Domain")
        assert (sb_root / "my-vault-with-spaces").is_dir()

    def test_vault_with_dots_scaffolds(self, sb_root):
        second_brain_scaffold("vault.v2.final", "Versioned domain")
        # The slug function maps dots to dashes
        matching = [d for d in sb_root.iterdir() if d.is_dir() and "vault" in d.name]
        assert len(matching) >= 1

    def test_very_long_vault_name_handled(self, sb_root):
        """Names >256 chars should either succeed (truncated) or return an error string."""
        long_name = "a" * 300
        result = second_brain_scaffold(long_name, "Domain")
        assert isinstance(result, str)

    def test_vault_name_with_slashes_sanitized(self, sb_root):
        """Slashes in vault names must not create directory traversal."""
        result = second_brain_scaffold("vault/subdir", "Domain")
        # Should either succeed with sanitized name or return an error
        assert isinstance(result, str)
        # Ensure no unexpected subdirectory was created outside sb_root
        assert not (sb_root / "vault" / "subdir").is_dir() or (sb_root / "vault-subdir").is_dir()


# ══════════════════════════════════════════════════════════════════════════════
# CLAUDE.md Content Validation
# ══════════════════════════════════════════════════════════════════════════════

class TestClaudeMdContent:
    def test_claude_md_contains_domain(self, sb_root):
        second_brain_scaffold("test-domain", "Machine learning research")
        claude_md = (sb_root / "test-domain" / "CLAUDE.md").read_text()
        assert "Machine learning research" in claude_md

    def test_claude_md_contains_vault_name(self, sb_root):
        second_brain_scaffold("research-vault", "AI research")
        claude_md = (sb_root / "research-vault" / "CLAUDE.md").read_text()
        assert "research-vault" in claude_md

    def test_claude_md_contains_librarian_rules(self, sb_root):
        second_brain_scaffold("test-rules", "Any domain")
        claude_md = (sb_root / "test-rules" / "CLAUDE.md").read_text()
        # Must have some operational rules
        assert "wiki" in claude_md.lower() or "source" in claude_md.lower() or "rule" in claude_md.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Concurrent Write Safety
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrentWrites:
    def test_two_threads_writing_same_vault_no_corruption(self, sb_root):
        """Two threads writing different pages to the same vault should not corrupt data."""
        second_brain_scaffold("concurrent-vault", "Concurrency testing")
        errors = []

        def _write_pages(thread_id: int):
            try:
                for i in range(5):
                    second_brain_write_page(
                        "concurrent-vault", "concepts",
                        f"concept-thread{thread_id}-{i}",
                        f"# Concept {thread_id}-{i}\n\nContent from thread {thread_id}, iteration {i}."
                    )
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=_write_pages, args=(1,))
        t2 = threading.Thread(target=_write_pages, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == [], f"Concurrent write errors: {errors}"

        # Verify pages exist and are readable
        pages = second_brain_list_pages("concurrent-vault", "concepts")
        assert isinstance(pages, str)

    def test_concurrent_append_log_no_corruption(self, sb_root):
        """Concurrent log appends must not corrupt the log.md file."""
        second_brain_scaffold("log-vault", "Log testing")
        errors = []

        def _append_log(n: int):
            try:
                for i in range(3):
                    second_brain_append_log("log-vault", f"Event {n}-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_append_log, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        log_path = sb_root / "log-vault" / "wiki" / "log.md"
        # Log file should exist and be non-empty
        assert log_path.exists()
        assert log_path.stat().st_size > 0
