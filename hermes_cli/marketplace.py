"""Community marketplace layer for Hermes skills.

Fetches a remote skill index, lets the user browse and search it, and
installs skills into ``~/.hermes/skills/`` with full provenance tracking.

Index format
------------
The index is a JSON file (served from any URL) with this structure::

    {
      "version": 1,
      "updated_at": "2026-01-01T00:00:00Z",
      "skills": [
        {
          "id": "proposal-writer",
          "name": "Proposal Writer",
          "description": "Generates client proposals from project details",
          "author": "Jane Doe",
          "version": "1.2.0",
          "tags": ["writing", "business"],
          "url": "https://example.com/skills/proposal-writer/SKILL.md",
          "homepage": "https://github.com/example/proposal-writer"
        },
        ...
      ]
    }

The default index URL can be overridden via the ``HERMES_MARKETPLACE_URL``
environment variable or ``marketplace.index_url`` in ``config.yaml``.

Public API
----------
  DEFAULT_INDEX_URL   str    canonical community index

  fetch_index(url)    → MarketplaceIndex
  search_index(index, query, tags)  → List[SkillEntry]
  install_from_entry(entry, *, force)  → InstallResult
  get_index_url()     → str   (respects env / config overrides)
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/NousResearch/hermes-skill-index/main/index.json"

_CONNECT_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SkillEntry:
    id: str
    name: str
    description: str
    author: str = ""
    version: str = "latest"
    tags: List[str] = field(default_factory=list)
    url: str = ""           # raw URL of the SKILL.md file
    homepage: str = ""      # optional repo / docs URL


@dataclass
class MarketplaceIndex:
    version: int
    updated_at: str
    skills: List[SkillEntry]
    source_url: str = ""


@dataclass
class InstallResult:
    success: bool
    skill_id: str
    path: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def get_index_url() -> str:
    """Return the marketplace index URL, respecting env + config overrides."""
    env = os.environ.get("HERMES_MARKETPLACE_URL", "").strip()
    if env:
        return env
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        url = cfg.get("marketplace", {}).get("index_url", "").strip()
        if url:
            return url
    except Exception:
        pass
    return DEFAULT_INDEX_URL


# ---------------------------------------------------------------------------
# Fetch & parse
# ---------------------------------------------------------------------------

def fetch_index(url: Optional[str] = None) -> MarketplaceIndex:
    """Download and parse the marketplace index from *url*.

    Raises ``MarketplaceError`` on network or parse failure.
    """
    target = url or get_index_url()
    try:
        req = urllib.request.Request(
            target,
            headers={"User-Agent": "hermes-agent/marketplace"},
        )
        with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:
        raise MarketplaceError(f"Failed to fetch index from {target}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MarketplaceError(f"Index is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise MarketplaceError("Index must be a JSON object")

    skills: List[SkillEntry] = []
    for item in data.get("skills", []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        skills.append(SkillEntry(
            id=item["id"],
            name=item.get("name", item["id"]),
            description=item.get("description", ""),
            author=item.get("author", ""),
            version=str(item.get("version", "latest")),
            tags=[str(t) for t in item.get("tags", [])],
            url=item.get("url", ""),
            homepage=item.get("homepage", ""),
        ))

    return MarketplaceIndex(
        version=int(data.get("version", 1)),
        updated_at=str(data.get("updated_at", "")),
        skills=skills,
        source_url=target,
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_index(
    index: MarketplaceIndex,
    query: str = "",
    tags: Optional[List[str]] = None,
) -> List[SkillEntry]:
    """Filter *index.skills* by *query* (substring, case-insensitive) and *tags*."""
    q = query.strip().lower()
    results = index.skills

    if q:
        results = [
            s for s in results
            if q in s.id.lower()
            or q in s.name.lower()
            or q in s.description.lower()
            or any(q in t.lower() for t in s.tags)
        ]

    if tags:
        lc_tags = {t.lower() for t in tags}
        results = [
            s for s in results
            if any(t.lower() in lc_tags for t in s.tags)
        ]

    return results


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def install_from_entry(entry: SkillEntry, *, force: bool = False) -> InstallResult:
    """Download and install a skill from a marketplace entry.

    Downloads the raw SKILL.md from *entry.url* into
    ``~/.hermes/skills/<id>/SKILL.md`` and registers provenance.

    Raises nothing — errors are returned in ``InstallResult.error``.
    """
    if not entry.url:
        return InstallResult(
            success=False,
            skill_id=entry.id,
            error="No download URL in index entry",
        )

    from hermes_constants import get_hermes_home
    skill_dir = Path(get_hermes_home()) / "skills" / entry.id
    skill_path = skill_dir / "SKILL.md"

    if skill_path.exists() and not force:
        return InstallResult(
            success=False,
            skill_id=entry.id,
            path=str(skill_path),
            error=f"Already installed at {skill_path}. Use force=True to overwrite.",
        )

    try:
        req = urllib.request.Request(
            entry.url,
            headers={"User-Agent": "hermes-agent/marketplace"},
        )
        with urllib.request.urlopen(req, timeout=_CONNECT_TIMEOUT) as resp:
            content = resp.read()
    except Exception as exc:
        return InstallResult(
            success=False,
            skill_id=entry.id,
            error=f"Download failed: {exc}",
        )

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path.write_bytes(content)
    except Exception as exc:
        return InstallResult(
            success=False,
            skill_id=entry.id,
            error=f"Write failed: {exc}",
        )

    # Register provenance
    try:
        from agent.components_registry import register_skill
        register_skill(
            entry.id,
            str(skill_path),
            source="community",
            origin=entry.url,
            version=entry.version,
            author=entry.author,
            description=entry.description,
        )
    except Exception:
        pass  # provenance failure never blocks install

    return InstallResult(
        success=True,
        skill_id=entry.id,
        path=str(skill_path),
    )


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class MarketplaceError(Exception):
    """Raised when the marketplace index cannot be fetched or parsed."""
