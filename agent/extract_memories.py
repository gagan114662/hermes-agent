# agent/extract_memories.py
"""
Auto-extract durable memories after each conversation.

After run_conversation() returns, a lightweight background thread
reviews the conversation for facts worth remembering and appends them
to the appropriate topic file in ~/.hermes/memories/.

Design:
- Runs in a daemon thread so it never blocks the response
- Uses a simple heuristic filter: only runs if conversation has ≥4 messages
- Calls a mini-LLM pass (uses the agent's own client) to extract facts
- Never modifies existing memories — only appends new ones
- Fails silently: errors never surface to the user
"""
from __future__ import annotations
import logging
import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from run_agent import AIAgent

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Review this conversation and extract any durable facts worth remembering.

Focus on:
- Contact details (names, companies, roles, preferences)
- Deal information (status, value, blockers, next steps)
- User preferences (how they like to work, communication style)
- Project context (goals, constraints, key decisions)

Rules:
- Only extract facts explicitly stated, never infer
- Skip small talk and one-off queries
- Each fact should be 1 concise sentence
- Output as a JSON list: [{{"topic": "contacts|deals|preferences|project", "fact": "..."}}]
- If nothing worth remembering, output: []

Conversation:
{conversation_summary}
"""


def _extract_and_save(
    messages: list,
    memories_dir: str,
    agent: "AIAgent",
) -> None:
    """Background extraction — runs in daemon thread."""
    try:
        if len(messages) < 4:
            return  # Too short to extract from

        # Build a compact conversation summary (last 20 messages max)
        recent = messages[-20:]
        summary_parts = []
        for m in recent:
            role = m.get("role", "")
            content = m.get("content", "")
            if isinstance(content, list):
                # Handle structured content blocks
                content = " ".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                )
            if role in ("user", "assistant") and content:
                summary_parts.append(f"{role.upper()}: {content[:200]}")

        if not summary_parts:
            return

        conversation_summary = "\n".join(summary_parts[:30])
        prompt = EXTRACTION_PROMPT.format(conversation_summary=conversation_summary)

        # Use a cheap model for extraction — use the agent's client
        try:
            resp = agent.client.chat.completions.create(
                model="anthropic/claude-haiku-4-5",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            raw = resp.choices[0].message.content or "[]"
        except Exception as e:
            logger.debug("extract_memories LLM call failed: %s", e)
            return

        # Parse JSON
        import json
        try:
            # Strip markdown code blocks if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            facts = json.loads(raw)
        except Exception:
            logger.debug("extract_memories: could not parse LLM output")
            return

        if not isinstance(facts, list) or not facts:
            return

        # Write to topic files
        os.makedirs(memories_dir, exist_ok=True)
        index_path = os.path.join(memories_dir, "MEMORY.md")

        # Group by topic
        from collections import defaultdict
        by_topic: dict[str, list[str]] = defaultdict(list)
        for item in facts:
            if isinstance(item, dict) and "fact" in item:
                topic = item.get("topic", "general")
                # Sanitize topic name for filename
                safe_topic = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
                by_topic[safe_topic].append(item["fact"])

        for topic, new_facts in by_topic.items():
            topic_file = os.path.join(memories_dir, f"{topic}.md")

            # Append facts
            with open(topic_file, "a") as f:
                for fact in new_facts:
                    f.write(f"- {fact}\n")

            # Update MEMORY.md index if topic is new
            if os.path.exists(index_path):
                with open(index_path) as f:
                    existing = f.read()
                if f"[{topic}.md]" not in existing:
                    with open(index_path, "a") as f:
                        f.write(f"- [{topic}.md]({topic}.md): Auto-extracted {topic} facts\n")
            else:
                with open(index_path, "w") as f:
                    f.write(f"- [{topic}.md]({topic}.md): Auto-extracted {topic} facts\n")

        logger.debug(
            "extract_memories: saved %d facts across %d topics",
            sum(len(v) for v in by_topic.values()),
            len(by_topic),
        )

    except Exception as e:
        logger.debug("extract_memories background thread error: %s", e)


def maybe_extract_memories(
    messages: list,
    agent: "AIAgent",
    memories_dir: str = None,
) -> None:
    """Fire-and-forget: extract memories from messages in a background thread.

    Called from _build_result() after a conversation completes.
    Never raises, never blocks.
    """
    if memories_dir is None:
        memories_dir = os.path.expanduser("~/.hermes/memories")

    t = threading.Thread(
        target=_extract_and_save,
        args=(messages, memories_dir, agent),
        daemon=True,
        name="extract-memories",
    )
    t.start()
