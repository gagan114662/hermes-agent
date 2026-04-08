"""
Magic Docs: files with '# MAGIC DOC: title' auto-update after conversations.

Any file read during an agent session that contains this header is registered.
After the conversation ends (via stop_hooks), a background thread uses the
conversation context to update the document with new information.

Only updates if there is "substantial new information" in the conversation.
"""
from __future__ import annotations
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAGIC_DOC_PATTERN = re.compile(r'^#\s*MAGIC\s+DOC:\s*(.+)$', re.MULTILINE | re.IGNORECASE)
ITALICS_PATTERN = re.compile(r'^\s*_(.+?)_\s*$')

@dataclass
class MagicDocEntry:
    path: str
    title: str
    instructions: str = ""  # Optional custom instructions from italics line after header

# Global registry — path → entry
_tracked_docs: dict[str, MagicDocEntry] = {}
_registry_lock = threading.Lock()


def detect_magic_doc(file_path: str, content: str) -> MagicDocEntry | None:
    """Return MagicDocEntry if file has MAGIC DOC header, else None."""
    match = MAGIC_DOC_PATTERN.search(content)
    if not match:
        return None

    title = match.group(1).strip()
    instructions = ""

    # Check for optional italics instructions on next non-empty line
    after_header = content[match.end():]
    lines = after_header.split('\n')
    for line in lines[:3]:  # Check first 3 lines after header
        line = line.strip()
        if not line:
            continue
        italics_match = ITALICS_PATTERN.match(line)
        if italics_match:
            instructions = italics_match.group(1).strip()
        break

    return MagicDocEntry(path=file_path, title=title, instructions=instructions)


def register_magic_doc(entry: MagicDocEntry) -> None:
    """Register a magic doc for post-conversation update."""
    with _registry_lock:
        if entry.path not in _tracked_docs:
            _tracked_docs[entry.path] = entry
            logger.debug("[magic-docs] Registered: %s (%s)", entry.path, entry.title)


def maybe_register_from_read(file_path: str, content: str) -> None:
    """Call this whenever a file is read. Registers if it's a magic doc."""
    entry = detect_magic_doc(file_path, content)
    if entry:
        register_magic_doc(entry)


def update_magic_docs_async(messages: list[dict], agent: Any) -> None:
    """Fire-and-forget: update all registered magic docs in background thread."""
    with _registry_lock:
        if not _tracked_docs:
            return
        docs = dict(_tracked_docs)

    threading.Thread(
        target=_update_docs_worker,
        args=(messages, agent, docs),
        daemon=True,
        name="magic-docs-updater",
    ).start()
    logger.debug("[magic-docs] Spawned updater thread for %d docs", len(docs))


def clear_registry() -> None:
    """Clear tracked docs (call at session start)."""
    with _registry_lock:
        _tracked_docs.clear()


def _update_docs_worker(messages: list[dict], agent: Any, docs: dict[str, MagicDocEntry]) -> None:
    """Background worker: updates each magic doc using conversation context."""
    for path, entry in docs.items():
        try:
            _update_single_doc(path, entry, messages, agent)
        except Exception as e:
            logger.debug("[magic-docs] Failed to update %s: %s", path, e)


def _update_single_doc(path: str, entry: MagicDocEntry, messages: list[dict], agent: Any) -> None:
    """Update a single magic doc using the conversation context."""
    doc_path = Path(path)
    if not doc_path.exists():
        logger.debug("[magic-docs] File no longer exists: %s", path)
        return

    current_content = doc_path.read_text(encoding='utf-8')

    # Build conversation summary for the LLM
    conversation_text = _summarize_messages(messages)
    if len(conversation_text) < 100:
        logger.debug("[magic-docs] Not enough conversation content to update %s", path)
        return

    # Build the update prompt
    instructions_note = f"\nUpdate instructions: {entry.instructions}" if entry.instructions else ""
    prompt = f"""You are updating a living document titled "{entry.title}".{instructions_note}

Current document content:
{current_content}

Recent conversation context:
{conversation_text[:3000]}

Task: Update the document to reflect any substantial new information from the conversation.
- Preserve the "# MAGIC DOC: {entry.title}" header exactly
- Only update if there is genuinely new, relevant information
- Keep the document concise and well-organized
- If nothing significant changed, return the document unchanged

Return ONLY the updated document content (no explanation, no markdown fences)."""

    try:
        from agent.auxiliary_client import call_llm
        response = call_llm(
            messages=[{"role": "user", "content": prompt}],
            model=getattr(agent, 'aux_model', None) or "claude-haiku-4-5",
            max_tokens=2000,
            base_url=getattr(agent, 'base_url', ''),
            api_key=getattr(agent, 'api_key', ''),
        )

        if response and response.choices:
            new_content = response.choices[0].message.content.strip()
            # Sanity check: must still have the magic doc header
            if MAGIC_DOC_PATTERN.search(new_content) and new_content != current_content:
                doc_path.write_text(new_content, encoding='utf-8')
                logger.info("[magic-docs] Updated: %s", path)
            else:
                logger.debug("[magic-docs] No substantial changes to %s", path)
    except Exception as e:
        logger.debug("[magic-docs] LLM call failed for %s: %s", path, e)


def _summarize_messages(messages: list[dict]) -> str:
    """Extract readable text from conversation messages."""
    parts = []
    for msg in messages[-20:]:  # Last 20 messages only
        role = msg.get('role', '')
        content = msg.get('content', '')
        if isinstance(content, str) and content:
            parts.append(f"{role}: {content[:500]}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    text = block.get('text', '')[:500]
                    if text:
                        parts.append(f"{role}: {text}")
                        break
    return '\n'.join(parts)
