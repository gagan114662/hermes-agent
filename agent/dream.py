# agent/dream.py
"""
Dream: nightly memory consolidation.

Fires a background agent that reviews recent session transcripts,
identifies patterns, and consolidates them into ~/.hermes/memories/.

Gate order (cheapest first):
1. Time: hours since last consolidation >= min_hours (default: 20h)
2. Sessions: new sessions since last run >= min_sessions (default: 3)
3. Lock: no other consolidation in progress

Ported from CC's services/autoDream/autoDream.ts.
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = os.path.expanduser("~/.hermes/memories/.dream_state.json")
LOCK_FILE = os.path.expanduser("~/.hermes/memories/.dream_lock")
MIN_HOURS = 20
MIN_SESSIONS = 3

CONSOLIDATION_PROMPT = """You are reviewing recent conversation sessions to consolidate memories.

Recent sessions summary:
{sessions_summary}

Current memories index:
{memory_index}

Tasks:
1. Identify durable patterns not yet in memory (repeated topics, consistent preferences, ongoing projects)
2. Identify outdated memories that should be updated
3. Generate a list of memory updates

Output JSON:
{{
  "new_facts": [{{"topic": "...", "fact": "..."}}],
  "summary": "one sentence describing what you consolidated"
}}
"""


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"last_consolidated_at": None, "sessions_at_last_run": 0}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_FILE)


def _acquire_lock() -> bool:
    """Returns True if lock acquired, False if already locked."""
    try:
        if os.path.exists(LOCK_FILE):
            # Check if lock is stale (>2 hours old)
            mtime = os.path.getmtime(LOCK_FILE)
            if time.time() - mtime < 7200:
                return False
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False


def _release_lock() -> None:
    try:
        os.remove(LOCK_FILE)
    except Exception:
        pass


def should_dream(min_hours: int = MIN_HOURS, min_sessions: int = MIN_SESSIONS) -> bool:
    """Check if consolidation should run now."""
    state = _load_state()

    # Time gate
    last = state.get("last_consolidated_at")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            hours_since = (datetime.utcnow() - last_dt).total_seconds() / 3600
            if hours_since < min_hours:
                return False
        except Exception:
            pass

    # Session count gate — count session files newer than last run
    sessions_dir = os.path.expanduser("~/.hermes/sessions")
    if not os.path.isdir(sessions_dir):
        return False

    cutoff = 0
    if last:
        try:
            cutoff = datetime.fromisoformat(last).timestamp()
        except Exception:
            pass

    new_sessions = sum(
        1 for f in os.listdir(sessions_dir)
        if os.path.getmtime(os.path.join(sessions_dir, f)) > cutoff
    )
    return new_sessions >= min_sessions


def run_dream(agent: "AIAgent") -> None:
    """Run memory consolidation synchronously. Called from background thread."""
    if not _acquire_lock():
        logger.debug("dream: another consolidation is running, skipping")
        return

    try:
        memories_dir = os.path.expanduser("~/.hermes/memories")
        index_path = os.path.join(memories_dir, "MEMORY.md")

        # Read memory index
        memory_index = ""
        if os.path.exists(index_path):
            with open(index_path) as f:
                memory_index = f.read()[:2000]

        # Summarize recent sessions (last 5)
        sessions_dir = os.path.expanduser("~/.hermes/sessions")
        sessions_summary = "No recent sessions found."
        if os.path.isdir(sessions_dir):
            session_files = sorted(
                [os.path.join(sessions_dir, f) for f in os.listdir(sessions_dir)],
                key=os.path.getmtime,
                reverse=True,
            )[:5]
            parts = []
            for sf in session_files:
                try:
                    with open(sf) as f:
                        content = f.read(1000)
                    parts.append(f"[{os.path.basename(sf)}]\n{content}")
                except Exception:
                    pass
            if parts:
                sessions_summary = "\n\n".join(parts)

        prompt = CONSOLIDATION_PROMPT.format(
            sessions_summary=sessions_summary[:3000],
            memory_index=memory_index,
        )

        # Call LLM
        # Inherit parent's prompt cache to avoid re-paying for cached prefix
        dream_messages: list = [{"role": "user", "content": prompt}]
        try:
            from agent.prompt_caching import get_last_cache_safe_params
            cache_params = get_last_cache_safe_params()
            if cache_params and cache_params.cached_messages_prefix:
                # Prepend parent's cached prefix so our first call hits the cache
                logger.debug(
                    "[dream] Inheriting %d cached messages from parent",
                    len(cache_params.cached_messages_prefix),
                )
                # Note: don't re-apply cache_control markers — they're already in the prefix
                dream_messages = list(cache_params.cached_messages_prefix) + dream_messages
        except ImportError:
            pass

        resp = agent.client.chat.completions.create(
            model="anthropic/claude-haiku-4-5",
            messages=dream_messages,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content or "{}"

        # Parse and save
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)

        new_facts = data.get("new_facts", [])
        if new_facts:
            # Write directly by topic
            from collections import defaultdict
            by_topic: dict = defaultdict(list)
            for item in new_facts:
                if isinstance(item, dict) and "fact" in item:
                    topic = item.get("topic", "general")
                    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
                    by_topic[safe].append(item["fact"])

            os.makedirs(memories_dir, exist_ok=True)
            for topic, facts in by_topic.items():
                topic_file = os.path.join(memories_dir, f"{topic}.md")
                with open(topic_file, "a") as f:
                    for fact in facts:
                        f.write(f"- [dream] {fact}\n")

        # Update state
        _save_state({
            "last_consolidated_at": datetime.utcnow().isoformat(),
            "sessions_at_last_run": 0,
            "last_summary": data.get("summary", ""),
        })
        logger.info("dream: consolidation complete — %s", data.get("summary", "done"))

    except Exception as e:
        logger.warning("dream: consolidation failed: %s", e)
    finally:
        _release_lock()


def maybe_dream(agent: "AIAgent") -> None:
    """Fire dream consolidation in background if gates pass. Never raises."""
    try:
        if not should_dream():
            return
        t = threading.Thread(
            target=run_dream,
            args=(agent,),
            daemon=True,
            name="hermes-dream",
        )
        t.start()
        logger.debug("dream: started background consolidation")
    except Exception as e:
        logger.debug("dream: failed to start: %s", e)
