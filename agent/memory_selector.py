"""Memory relevance scoring for topic-file layout.

Selects the most relevant topic files from ~/.hermes/memories/ based on
keyword overlap with the user message. No LLM calls — pure keyword matching.

Topic-file layout:
  ~/.hermes/memories/
    MEMORY.md          # index: one line per topic file
    personal.md        # always included
    <topic>.md         # per-topic memory files

Index format (MEMORY.md):
  - [topic_name.md](topic_name.md): one-line description
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens from text."""
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def _score_topic(user_tokens: set[str], topic_name: str, description: str) -> int:
    """Score a topic by keyword overlap with user message tokens."""
    topic_tokens = _tokenize(topic_name + " " + description)
    return len(user_tokens & topic_tokens)


def _parse_index(index_content: str) -> list[tuple[str, str]]:
    """Parse MEMORY.md index lines.

    Expected format:
      - [filename.md](filename.md): description text

    Returns list of (filename, description) tuples.
    """
    entries = []
    for line in index_content.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        # Extract filename from markdown link: [name](filename.md)
        link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', line)
        if not link_match:
            continue
        filename = link_match.group(2).strip()
        # Extract description after the colon
        after_link = line[line.index(link_match.group(0)) + len(link_match.group(0)):]
        description = after_link.lstrip(": ").strip()
        entries.append((filename, description))
    return entries


def select_relevant_memories(
    user_message: str,
    memories_dir: str,
    max_topics: int = 5,
    max_chars_per_topic: int = 800,
) -> str:
    """Select the most relevant topic files from the memories directory.

    Strategy (no LLM call — keyword matching only):
    1. Read MEMORY.md index to get list of topics + descriptions
    2. Score each topic: count keyword overlaps between user_message and
       topic name + description
    3. Always include 'personal.md' if it exists (universal relevance)
    4. Return top max_topics topics concatenated (with headers)

    Falls back gracefully:
    - If memories_dir doesn't exist: returns ""
    - If MEMORY.md doesn't exist: returns ""
    - If individual topic file can't be read: skips it silently
    """
    dir_path = Path(memories_dir)
    if not dir_path.is_dir():
        return ""

    index_path = dir_path / "MEMORY.md"
    if not index_path.exists():
        return ""

    try:
        index_content = index_path.read_text(encoding="utf-8")
    except (OSError, IOError):
        return ""

    entries = _parse_index(index_content)
    if not entries:
        return ""

    user_tokens = _tokenize(user_message)

    # Score topics and sort by relevance
    scored: list[tuple[int, str, str]] = []  # (score, filename, description)
    has_personal = False

    for filename, description in entries:
        if filename == "personal.md":
            has_personal = True
            # personal.md is always included — don't put it in the scored list
            # (we'll prepend it separately)
            continue
        score = _score_topic(user_tokens, filename, description)
        scored.append((score, filename, description))

    # Sort by score descending, then by filename for stable ordering
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Build selected list: personal.md first (if exists), then top-N by score
    selected_files: list[str] = []
    if has_personal and (dir_path / "personal.md").exists():
        selected_files.append("personal.md")

    # Fill remaining slots with top-scored topics
    remaining_slots = max_topics - len(selected_files)
    for _score, filename, _desc in scored[:remaining_slots]:
        topic_path = dir_path / filename
        if topic_path.exists():
            selected_files.append(filename)

    if not selected_files:
        return ""

    # Read and concatenate selected topic files
    sections: list[str] = []
    for filename in selected_files:
        topic_path = dir_path / filename
        try:
            content = topic_path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            # Truncate if needed
            if len(content) > max_chars_per_topic:
                content = content[:max_chars_per_topic] + f"\n[...truncated {filename}]"
            sections.append(content)
        except (OSError, IOError) as e:
            logger.debug("Could not read topic file %s: %s", topic_path, e)

    return "\n\n".join(sections)
