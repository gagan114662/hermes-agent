"""
Second Brain Tool — Multi-Vault Domain Knowledge System

Pure file I/O layer. No LLM calls — the agent (Claude) handles all synthesis
and writing via the skill instructions. These tools just manage the vault
structure so the agent has clean primitives to work with.

Structure (per vault):
    ~/.hermes/second-brain/{vault-name}/
        raw/                ← drop source files here
        wiki/
            sources/        ← one summary .md per ingested source
            entities/       ← people, tools, companies
            concepts/       ← ideas, frameworks, theories
            synthesis/      ← comparisons and analyses
            index.md        ← master catalog of all pages
            log.md          ← timeline of ingestions and queries
        output/             ← saved query results and reports
        CLAUDE.md           ← domain config and librarian rules

Tools (dumb file I/O only — agent does the thinking):
    second_brain_scaffold(vault_name, domain)        — create a new vault
    second_brain_list()                              — list all vaults
    second_brain_raw_list(vault_name)                — list unprocessed raw/ files
    second_brain_read_source(vault_name, filename)   — read a raw/ file
    second_brain_write_page(vault_name, section, page_name, content) — write a wiki page
    second_brain_read_page(vault_name, section, page_name) — read a wiki page
    second_brain_list_pages(vault_name, section)     — list pages in a wiki section
    second_brain_append_log(vault_name, entry)       — append to activity log
    second_brain_lint(vault_name)                    — audit wiki health
"""

import os
import re
from datetime import datetime
from pathlib import Path

from tools.registry import registry


# ── storage helpers ───────────────────────────────────────────────────────────

def _sb_root() -> Path:
    d = Path(os.path.expanduser("~/.hermes/second-brain"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip()).strip("-")
    return slug[:200]  # keep well within filesystem 255-byte component limit


def _vault_dir(vault_name: str) -> Path:
    return _sb_root() / _slug(vault_name)


def _vault_exists(vault_name: str) -> bool:
    return (_vault_dir(vault_name) / "CLAUDE.md").exists()


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── scaffold ──────────────────────────────────────────────────────────────────

_CLAUDE_MD_TEMPLATE = """# Second Brain: {vault_name}

**Domain:** {domain}
**Created:** {created}

## Librarian Rules

- Every source ingested goes in wiki/sources/ with a summary page
- People, tools, and companies get their own pages in wiki/entities/
- Ideas and frameworks go in wiki/concepts/
- Cross-reference liberally — link related pages using [[page-name]] syntax
- Update wiki/index.md and wiki/log.md after every operation
- Save synthesis/ pages when queries surface non-obvious patterns
- Raw sources in raw/ are inputs only — never edit them directly

## Domain Focus

This vault is dedicated to: {domain}
"""

_INDEX_TEMPLATE = """# {vault_name} — Wiki Index

**Domain:** {domain}
**Created:** {created}

## Sources
*No sources ingested yet.*

## Entities
*No entity pages yet.*

## Concepts
*No concept pages yet.*

## Synthesis
*No synthesis pages yet.*
"""


def second_brain_scaffold(vault_name: str, domain: str) -> str:
    """
    Create a new domain-specific second brain vault. Sets up folder structure
    and writes the CLAUDE.md config. Agent should call this once per domain.

    Args:
        vault_name: Short slug for the vault (e.g. 'hermes-agent', 'personal-health')
        domain: What this vault covers (1-2 sentences)
    """
    slug = _slug(vault_name)
    vault = _sb_root() / slug

    if (vault / "CLAUDE.md").exists():
        return f"Vault '{slug}' already exists at {vault}. Use second_brain_list() to see all vaults."

    for subdir in ["raw", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/synthesis", "output"]:
        (vault / subdir).mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d")
    _write_file(vault / "CLAUDE.md", _CLAUDE_MD_TEMPLATE.format(
        vault_name=vault_name, domain=domain, created=now,
    ))
    _write_file(vault / "wiki" / "index.md", _INDEX_TEMPLATE.format(
        vault_name=vault_name, domain=domain, created=now,
    ))
    _write_file(vault / "wiki" / "log.md", f"# {vault_name} — Activity Log\n\n")

    return (
        f"Vault '{vault_name}' created at {vault}\n\n"
        f"Structure:\n"
        f"  raw/              ← drop source files here\n"
        f"  wiki/sources/     ← one summary page per source\n"
        f"  wiki/entities/    ← people, tools, companies\n"
        f"  wiki/concepts/    ← ideas, frameworks, theories\n"
        f"  wiki/synthesis/   ← saved analyses\n"
        f"  output/           ← query results\n"
        f"  CLAUDE.md         ← domain rules"
    )


# ── list ──────────────────────────────────────────────────────────────────────

def second_brain_list() -> str:
    """List all second brain vaults with domain, page counts, and unprocessed files."""
    root = _sb_root()
    vaults = [d for d in sorted(root.iterdir()) if d.is_dir() and (d / "CLAUDE.md").exists()]

    if not vaults:
        return "No vaults found. Create one with second_brain_scaffold(vault_name, domain)."

    lines = [f"Second Brain Vaults ({len(vaults)}):\n"]
    for vault in vaults:
        claude_md = _read_file(vault / "CLAUDE.md")
        domain_match = re.search(r"\*\*Domain:\*\*\s*(.+)", claude_md)
        domain = domain_match.group(1).strip() if domain_match else "unknown"

        wiki_pages = list((vault / "wiki").rglob("*.md")) if (vault / "wiki").exists() else []
        page_count = len([p for p in wiki_pages if p.name not in ("index.md", "log.md")])

        raw_dir = vault / "raw"
        sources_dir = vault / "wiki" / "sources"
        raw_files = [f for f in raw_dir.glob("*") if f.is_file() and not f.name.startswith(".")] if raw_dir.exists() else []
        unprocessed = [f for f in raw_files if not (sources_dir / f"{f.stem}.md").exists()]

        lines.append(
            f"  {vault.name}/\n"
            f"    Domain:      {domain}\n"
            f"    Wiki pages:  {page_count}\n"
            f"    Unprocessed: {len(unprocessed)} raw files\n"
            f"    Path:        {vault}\n"
        )

    return "\n".join(lines)


# ── raw file access ───────────────────────────────────────────────────────────

def second_brain_raw_list(vault_name: str) -> str:
    """
    List files in the vault's raw/ directory, showing which are already
    processed (have a wiki/sources/ page) and which are not yet ingested.

    Args:
        vault_name: Name of the vault
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found. Use second_brain_list() to see available vaults."

    vault = _vault_dir(vault_name)
    raw_dir = vault / "raw"
    sources_dir = vault / "wiki" / "sources"

    raw_files = sorted([f for f in raw_dir.glob("*") if f.is_file() and not f.name.startswith(".")])

    if not raw_files:
        return f"No files in {raw_dir}. Drop source files there to get started."

    lines = [f"raw/ files in vault '{vault_name}':\n"]
    for f in raw_files:
        processed = (sources_dir / f"{f.stem}.md").exists()
        size = f.stat().st_size
        status = "✓ ingested" if processed else "○ not yet ingested"
        lines.append(f"  {f.name} ({size:,} bytes) — {status}")

    unprocessed = [f for f in raw_files if not (sources_dir / f"{f.stem}.md").exists()]
    lines.append(f"\n{len(unprocessed)} of {len(raw_files)} files need ingestion.")
    return "\n".join(lines)


def second_brain_read_source(vault_name: str, filename: str) -> str:
    """
    Read a raw/ source file so the agent can process it. Returns the full content.

    Args:
        vault_name: Name of the vault
        filename: Filename in raw/ (e.g. 'readme.md')
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found."

    vault = _vault_dir(vault_name)
    src = vault / "raw" / filename

    if not src.exists():
        available = [f.name for f in (vault / "raw").glob("*") if f.is_file()]
        return f"File '{filename}' not found. Available: {', '.join(available)}"

    content = _read_file(src)
    return f"=== {filename} ({len(content):,} chars) ===\n\n{content}"


# ── wiki page access ──────────────────────────────────────────────────────────

_VALID_SECTIONS = {"sources", "entities", "concepts", "synthesis"}


def second_brain_write_page(vault_name: str, section: str, page_name: str, content: str) -> str:
    """
    Write a wiki page. Agent calls this to create/update sources, entities,
    concepts, and synthesis pages after processing a source.

    Args:
        vault_name: Name of the vault
        section: One of: sources, entities, concepts, synthesis
        page_name: Filename without .md (e.g. 'andrej-karpathy', 'llm-wiki-pattern')
        content: Full markdown content for the page
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found."

    if section not in _VALID_SECTIONS:
        return f"Invalid section '{section}'. Use one of: {', '.join(_VALID_SECTIONS)}"

    vault = _vault_dir(vault_name)
    slug = _slug(page_name)
    page_path = vault / "wiki" / section / f"{slug}.md"
    _write_file(page_path, content)

    return f"Written: wiki/{section}/{slug}.md ({len(content):,} chars)"


def second_brain_read_page(vault_name: str, section: str, page_name: str) -> str:
    """
    Read an existing wiki page.

    Args:
        vault_name: Name of the vault
        section: One of: sources, entities, concepts, synthesis (or 'index', 'log')
        page_name: Filename without .md
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found."

    vault = _vault_dir(vault_name)

    if section in ("index", "log"):
        path = vault / "wiki" / f"{section}.md"
    elif section in _VALID_SECTIONS:
        path = vault / "wiki" / section / f"{_slug(page_name)}.md"
    else:
        return f"Invalid section '{section}'."

    content = _read_file(path)
    return content if content else f"Page not found: wiki/{section}/{page_name}.md"


def second_brain_list_pages(vault_name: str, section: str = "all") -> str:
    """
    List wiki pages in a section (or all sections).

    Args:
        vault_name: Name of the vault
        section: 'all', 'sources', 'entities', 'concepts', or 'synthesis'
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found."

    vault = _vault_dir(vault_name)
    wiki = vault / "wiki"

    sections_to_show = list(_VALID_SECTIONS) if section == "all" else [section]
    lines = [f"Wiki pages in '{vault_name}':\n"]

    for sec in sections_to_show:
        subdir = wiki / sec
        pages = sorted(subdir.glob("*.md")) if subdir.exists() else []
        lines.append(f"  {sec}/ ({len(pages)} pages)")
        for p in pages:
            size = p.stat().st_size
            lines.append(f"    - {p.stem} ({size:,} bytes)")

    return "\n".join(lines)


def second_brain_append_log(vault_name: str, entry: str) -> str:
    """
    Append a timestamped entry to the vault's activity log.

    Args:
        vault_name: Name of the vault
        entry: What happened (e.g. 'Ingested readme.md — created 3 entity pages, 4 concept pages')
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found."

    log_path = _vault_dir(vault_name) / "wiki" / "log.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = _read_file(log_path)
    _write_file(log_path, f"{existing}- {ts} — {entry}\n")
    return f"Log updated."


def second_brain_update_index(vault_name: str) -> str:
    """
    Rebuild the vault's wiki/index.md from the current page state.
    Call this after bulk ingestion to keep the index current.

    Args:
        vault_name: Name of the vault
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found."

    vault = _vault_dir(vault_name)
    wiki = vault / "wiki"

    claude_md = _read_file(vault / "CLAUDE.md")
    domain_match = re.search(r"\*\*Domain:\*\*\s*(.+)", claude_md)
    domain = domain_match.group(1).strip() if domain_match else "unknown"

    index = f"# {vault_name} — Wiki Index\n\n**Domain:** {domain}\n\n"

    for sec in ["sources", "entities", "concepts", "synthesis"]:
        subdir = wiki / sec
        pages = sorted(subdir.glob("*.md")) if subdir.exists() else []
        index += f"## {sec.title()}\n"
        if pages:
            for p in pages:
                index += f"- [[{sec}/{p.stem}]]\n"
        else:
            index += f"*No {sec} yet.*\n"
        index += "\n"

    _write_file(wiki / "index.md", index)
    return f"index.md rebuilt with {sum(1 for s in ['sources','entities','concepts','synthesis'] for _ in (wiki/s).glob('*.md') if (wiki/s).exists())} pages."


# ── lint ──────────────────────────────────────────────────────────────────────

def second_brain_lint(vault_name: str) -> str:
    """
    Audit vault health: broken links, orphan pages, unprocessed raw files,
    stub pages.

    Args:
        vault_name: Name of the vault to audit
    """
    if not _vault_exists(vault_name):
        return f"Vault '{vault_name}' not found."

    vault = _vault_dir(vault_name)
    wiki = vault / "wiki"
    issues: list[str] = []
    ok_count = 0

    all_wiki_pages: set[str] = set()
    for sub in _VALID_SECTIONS:
        subdir = wiki / sub
        if subdir.exists():
            for page in subdir.glob("*.md"):
                all_wiki_pages.add(f"{sub}/{page.stem}")

    # Broken links
    broken: list[str] = []
    for sub in _VALID_SECTIONS:
        subdir = wiki / sub
        if subdir.exists():
            for page in subdir.glob("*.md"):
                refs = re.findall(r"\[\[([^\]]+)\]\]", _read_file(page))
                for ref in refs:
                    ref_stem = ref.replace("wiki/", "").split("/")[-1]
                    if not any(p.endswith(ref_stem) for p in all_wiki_pages):
                        broken.append(f"  [[{ref}]] in wiki/{sub}/{page.stem}.md")
    if broken:
        issues.append(f"Broken links ({len(broken)}):\n" + "\n".join(broken))
    else:
        ok_count += 1

    # Orphan pages
    index_content = _read_file(wiki / "index.md")
    all_refs: set[str] = set()
    for sub in _VALID_SECTIONS:
        subdir = wiki / sub
        if subdir.exists():
            for page in subdir.glob("*.md"):
                refs = re.findall(r"\[\[([^\]]+)\]\]", _read_file(page))
                all_refs.update(r.split("/")[-1] for r in refs)
    all_refs.update(re.findall(r"\[\[([^\]]+)\]\]", index_content))

    orphans = [f"  wiki/{p}.md" for p in all_wiki_pages if p.split("/")[-1] not in all_refs and p not in index_content]
    if orphans:
        issues.append(f"Orphan pages ({len(orphans)}):\n" + "\n".join(orphans))
    else:
        ok_count += 1

    # Unprocessed raw
    raw_dir = vault / "raw"
    sources_dir = wiki / "sources"
    unprocessed = [
        f"  {f.name}" for f in raw_dir.glob("*")
        if f.is_file() and not f.name.startswith(".") and not (sources_dir / f"{f.stem}.md").exists()
    ] if raw_dir.exists() else []
    if unprocessed:
        issues.append(f"Unprocessed raw files ({len(unprocessed)}):\n" + "\n".join(unprocessed))
    else:
        ok_count += 1

    # Stubs
    stubs = [
        f"  wiki/{sub}/{page.stem}.md"
        for sub in _VALID_SECTIONS
        for page in ((wiki / sub).glob("*.md") if (wiki / sub).exists() else [])
        if len(_read_file(page).strip()) < 50
    ]
    if stubs:
        issues.append(f"Stub pages ({len(stubs)}):\n" + "\n".join(stubs))
    else:
        ok_count += 1

    if not issues:
        return f"Vault '{vault_name}' — lint passed ✓\n  {len(all_wiki_pages)} pages checked, no issues."

    return (
        f"Vault '{vault_name}' — lint ({ok_count}/{ok_count + len(issues)} checks passed)\n\n"
        + "\n\n".join(issues)
        + f"\n\nTotal wiki pages: {len(all_wiki_pages)}"
    )


# ── registry ──────────────────────────────────────────────────────────────────

registry.register(
    name="second_brain_scaffold",
    toolset="second-brain",
    schema={
        "name": "second_brain_scaffold",
        "description": "Create a new domain-specific second brain vault with full folder structure.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Short slug for the vault (e.g. 'hermes-agent', 'personal-health')"},
                "domain": {"type": "string", "description": "What this vault covers in 1-2 sentences"},
            },
            "required": ["vault_name", "domain"],
        },
    },
    handler=lambda args, **kw: second_brain_scaffold(args["vault_name"], args["domain"]),
)

registry.register(
    name="second_brain_list",
    toolset="second-brain",
    schema={
        "name": "second_brain_list",
        "description": "List all second brain vaults with domain, page counts, and unprocessed file count.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: second_brain_list(),
)

registry.register(
    name="second_brain_raw_list",
    toolset="second-brain",
    schema={
        "name": "second_brain_raw_list",
        "description": "List files in a vault's raw/ directory, showing which have been ingested and which haven't.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault"},
            },
            "required": ["vault_name"],
        },
    },
    handler=lambda args, **kw: second_brain_raw_list(args["vault_name"]),
)

registry.register(
    name="second_brain_read_source",
    toolset="second-brain",
    schema={
        "name": "second_brain_read_source",
        "description": "Read a raw/ source file to process it. Returns full content for the agent to analyze and extract entities/concepts from.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault"},
                "filename": {"type": "string", "description": "Filename in raw/ (e.g. 'readme.md')"},
            },
            "required": ["vault_name", "filename"],
        },
    },
    handler=lambda args, **kw: second_brain_read_source(args["vault_name"], args["filename"]),
)

registry.register(
    name="second_brain_write_page",
    toolset="second-brain",
    schema={
        "name": "second_brain_write_page",
        "description": "Write a wiki page (source summary, entity page, concept page, or synthesis). Call this after reading and analyzing a source file.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault"},
                "section": {"type": "string", "enum": ["sources", "entities", "concepts", "synthesis"], "description": "Wiki section to write to"},
                "page_name": {"type": "string", "description": "Page name without .md (e.g. 'andrej-karpathy', 'llm-wiki-pattern')"},
                "content": {"type": "string", "description": "Full markdown content for the page"},
            },
            "required": ["vault_name", "section", "page_name", "content"],
        },
    },
    handler=lambda args, **kw: second_brain_write_page(
        args["vault_name"], args["section"], args["page_name"], args["content"]
    ),
)

registry.register(
    name="second_brain_read_page",
    toolset="second-brain",
    schema={
        "name": "second_brain_read_page",
        "description": "Read an existing wiki page to check or update it.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault"},
                "section": {"type": "string", "description": "Section: sources, entities, concepts, synthesis, index, or log"},
                "page_name": {"type": "string", "description": "Page name without .md"},
            },
            "required": ["vault_name", "section", "page_name"],
        },
    },
    handler=lambda args, **kw: second_brain_read_page(
        args["vault_name"], args["section"], args["page_name"]
    ),
)

registry.register(
    name="second_brain_list_pages",
    toolset="second-brain",
    schema={
        "name": "second_brain_list_pages",
        "description": "List wiki pages in a vault section.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault"},
                "section": {"type": "string", "description": "'all', 'sources', 'entities', 'concepts', or 'synthesis'"},
            },
            "required": ["vault_name"],
        },
    },
    handler=lambda args, **kw: second_brain_list_pages(
        args["vault_name"], args.get("section", "all")
    ),
)

registry.register(
    name="second_brain_append_log",
    toolset="second-brain",
    schema={
        "name": "second_brain_append_log",
        "description": "Append a timestamped entry to the vault activity log.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault"},
                "entry": {"type": "string", "description": "Log entry describing what happened"},
            },
            "required": ["vault_name", "entry"],
        },
    },
    handler=lambda args, **kw: second_brain_append_log(args["vault_name"], args["entry"]),
)

registry.register(
    name="second_brain_update_index",
    toolset="second-brain",
    schema={
        "name": "second_brain_update_index",
        "description": "Rebuild wiki/index.md from current page state. Call after bulk ingestion.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault"},
            },
            "required": ["vault_name"],
        },
    },
    handler=lambda args, **kw: second_brain_update_index(args["vault_name"]),
)

registry.register(
    name="second_brain_lint",
    toolset="second-brain",
    schema={
        "name": "second_brain_lint",
        "description": "Audit vault health: broken links, orphan pages, unprocessed raw files, stub pages.",
        "parameters": {
            "type": "object",
            "properties": {
                "vault_name": {"type": "string", "description": "Name of the vault to audit"},
            },
            "required": ["vault_name"],
        },
    },
    handler=lambda args, **kw: second_brain_lint(args["vault_name"]),
)
