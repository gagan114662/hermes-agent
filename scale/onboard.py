#!/usr/bin/env python3
"""
Hermes Worker Onboarding

One-command deployment: describe your business, get a fully custom AI worker.
No templates. No picking from a menu. The LLM designs the worker from scratch.

Usage:
    python3 scale/onboard.py \
      --business-name "Mario's Pizza" \
      --business-info "Family-owned pizzeria in Brooklyn..." \
      --telegram-token "BOT_TOKEN" \
      --manager-chat-id "CHAT_ID"

Env vars:
    DATABASE_URL        postgresql://hermes:pass@localhost:5432/hermes
    REDIS_URL           redis://localhost:6379
    OPENROUTER_API_KEY  your key
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import redis.asyncio as aioredis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Worker generation prompt
# ---------------------------------------------------------------------------

GENERATE_WORKER_PROMPT = """You are designing an AI worker for a real business. Based on the description below, \
design the perfect autonomous AI employee for this specific business.

Business Name: {business_name}
Business Description:
{business_info}

Available toolsets (use exact keys from this list only):
- web: web search, URL reading, research
- reach: RSS feeds, YouTube search/transcripts
- file: read/write files in the worker's filesystem
- memory: persistent key-value memory
- session_search: search past conversations
- code_execution: run Python code
- delegation: spawn sub-agents for parallel work
- image_gen: generate images (requires FAL_KEY)
- social_media: post to Twitter/LinkedIn/Instagram
- social_media_direct: DMs and direct outreach
- browser: full browser automation
- vision: analyze images and screenshots
- terminal: run shell commands
- google-workspace: Gmail, Docs, Sheets, Calendar
- cronjob: schedule future tasks

Generate a complete worker profile as pure JSON (no markdown fences, no explanation — just JSON):
{{
  "name": "a real human first name that fits the worker's personality — not generic like Alex or Sam",
  "role": "a specific job title that matches exactly what this business needs — not a generic role",
  "personality": "3-4 sentences describing how this person thinks, communicates, and approaches problems",
  "goals": ["concrete goal 1", "concrete goal 2", "concrete goal 3", "concrete goal 4"],
  "toolsets": ["tool1", "tool2"],
  "system_prompt": "FULL system prompt for this worker, 600-900 words. Must include: (1) worker identity and personality, (2) business context in detail, (3) concrete goals and success metrics, (4) working principles, (5) filesystem location, (6) emphasis on proactive initiative and never waiting for instructions, (7) the tool fallback rules block verbatim at the end.",
  "first_week_priorities": ["specific actionable priority 1", "specific actionable priority 2", "specific actionable priority 3"],
  "gaps_identified": ["specific gap or opportunity 1", "specific gap or opportunity 2", "specific gap or opportunity 3"],
  "why": "2-3 sentences explaining why this specific worker design fits this specific business"
}}

The system_prompt must end with this exact block verbatim:
## Tool Fallback Rules — always try before saying you can't:
- web_search fails → use terminal: curl -s "https://duckduckgo.com/html/?q=QUERY" | grep -o 'class="result__snippet">[^<]*' | sed 's/[^>]*>//g' | head -5
- browser fails → use jina_read or web_extract on the URL instead
- email tool fails → draft the message and send instructions to manager
- social_post fails → write the copy and note it needs manual posting
- image_generate fails → describe the image in detail
Never say "I don't have access" or "I can't do that." Find another way.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.rstrip())
    return json.loads(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Onboard a new Hermes AI worker")
    parser.add_argument("--business-name", required=True, help="Business display name")
    parser.add_argument("--business-info", required=True, help="Description of the business (the more detail, the better)")
    parser.add_argument("--telegram-token", required=True, help="Telegram bot token for this worker")
    parser.add_argument("--manager-chat-id", required=True, help="Telegram chat ID to send proactive updates to")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "postgresql://hermes:hermes@localhost:5432/hermes")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    print(f"\n🔍 Analyzing {args.business_name}...")

    # ── Step 1: Generate worker identity from scratch ──────────────────────
    from run_agent import AIAgent

    design_agent = AIAgent(
        model="google/gemini-2.5-flash-preview",
        api_key=openrouter_key,
        base_url="https://openrouter.ai/api/v1",
        provider="openrouter",
        max_iterations=3,
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=[],
    )
    result = design_agent.run_conversation(
        user_message=GENERATE_WORKER_PROMPT.format(
            business_name=args.business_name,
            business_info=args.business_info,
        )
    )

    raw_response = result.get("final_response", "")
    try:
        worker = parse_json_response(raw_response)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"❌ Failed to parse worker design: {e}")
        print(f"Raw response:\n{raw_response[:500]}")
        sys.exit(1)

    worker_name = worker["name"]
    worker_role = worker["role"]
    toolsets = worker["toolsets"]
    system_prompt_base = worker["system_prompt"]
    gaps = worker.get("gaps_identified", [])
    priorities = worker.get("first_week_priorities", [])

    print(f"✓ Worker designed: {worker_name} ({worker_role})")

    # ── Step 2: Provision filesystem ───────────────────────────────────────
    tenant_id = uuid.uuid4()
    worker_home = Path.home() / ".hermes" / "workers" / str(tenant_id)
    for subdir in ["inbox", "drafts", "reports"]:
        (worker_home / subdir).mkdir(parents=True, exist_ok=True)

    # Append workspace info to system prompt
    workspace_block = f"""
## Your Workspace
Your personal filesystem is at: {worker_home}
- {worker_home}/inbox/    — emails and briefs you receive
- {worker_home}/drafts/   — work in progress (save everything here)
- {worker_home}/reports/  — completed deliverables

Always save your work here. Files persist between sessions.
When you start a task, check if you have relevant drafts or research already saved.
"""
    system_prompt = system_prompt_base + workspace_block

    # ── Step 3: Generate worker email ─────────────────────────────────────
    slug = slugify(args.business_name)
    worker_email = f"{worker_name.lower()}-{slug}@hermes-worker.com"

    # ── Step 4: Insert into Postgres ───────────────────────────────────────
    db = await asyncpg.create_pool(database_url, min_size=1, max_size=3)

    standing_instructions = (
        f"Focus on: {', '.join(priorities[:2])}" if priorities
        else "Do your best work and show initiative."
    )

    await db.execute("""
        INSERT INTO tenants (
            id, name, slug, system_prompt_template, enabled_toolsets,
            tenant_config, worker_email, active
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, true)
    """,
        tenant_id,
        args.business_name,
        slug,
        system_prompt,
        toolsets,
        json.dumps({
            "manager_chat_id": args.manager_chat_id,
            "worker_name": worker_name,
            "worker_role": worker_role,
            "standing_instructions": standing_instructions,
            "gaps_identified": gaps,
        }),
        worker_email,
    )

    # ── Step 5: Seed memory ────────────────────────────────────────────────
    await db.execute("""
        INSERT INTO tenant_memory (tenant_id, memory_type, content)
        VALUES ($1, 'business_info', $2)
        ON CONFLICT (tenant_id, memory_type) DO UPDATE SET content = EXCLUDED.content
    """, tenant_id, args.business_info)

    if priorities:
        await db.execute("""
            INSERT INTO tenant_memory (tenant_id, memory_type, content)
            VALUES ($1, 'first_week_priorities', $2)
            ON CONFLICT (tenant_id, memory_type) DO UPDATE SET content = EXCLUDED.content
        """, tenant_id, "\n".join(f"- {p}" for p in priorities))

    if gaps:
        await db.execute("""
            INSERT INTO tenant_memory (tenant_id, memory_type, content)
            VALUES ($1, 'gaps_identified', $2)
            ON CONFLICT (tenant_id, memory_type) DO UPDATE SET content = EXCLUDED.content
        """, tenant_id, "\n".join(f"- {g}" for g in gaps))

    # ── Step 6: Add Telegram platform ─────────────────────────────────────
    await db.execute("""
        INSERT INTO tenant_platforms (tenant_id, platform, bot_token)
        VALUES ($1, 'telegram', $2)
        ON CONFLICT (tenant_id, platform) DO UPDATE SET bot_token = EXCLUDED.bot_token
    """, tenant_id, args.telegram_token)

    await db.close()

    # ── Step 7: Send welcome message via Redis ─────────────────────────────
    redis = aioredis.from_url(redis_url, decode_responses=True)

    gaps_text = "\n".join(f"• {g}" for g in gaps) if gaps else "• Several growth opportunities identified"
    welcome = (
        f"Hi! I'm {worker_name}, your AI {worker_role}.\n\n"
        f"I've reviewed {args.business_name} and identified these opportunities:\n"
        f"{gaps_text}\n\n"
        f"My email: {worker_email} — CC me on anything.\n\n"
        f"I'm getting started right away. I'll check in as I make progress."
    )
    await redis.lpush("hermes:responses", json.dumps({
        "tenant_id": str(tenant_id),
        "platform": "telegram",
        "chat_id": args.manager_chat_id,
        "response": welcome,
    }))
    await redis.aclose()

    # ── Step 8: Restart gateway ────────────────────────────────────────────
    print("↻  Restarting gateway to pick up new tenant...")
    subprocess.run(
        ["docker", "compose", "-f", "scale/docker-compose.scale.yml", "restart", "gateway"],
        check=False,
        capture_output=True,
    )

    # ── Step 9: Print deployment summary ──────────────────────────────────
    print(f"\n{'='*60}")
    print(f"✓  Worker deployed: {worker_name} ({worker_role})")
    print(f"   Tenant ID:   {tenant_id}")
    print(f"   Slug:        {slug}")
    print(f"   Email:       {worker_email}")
    print(f"   Filesystem:  {worker_home}")
    print(f"   Toolsets:    {', '.join(toolsets)}")
    print(f"\n   Why this worker:")
    print(f"   {worker.get('why', '')}")
    if gaps:
        print(f"\n   Gaps identified:")
        for g in gaps:
            print(f"   • {g}")
    if priorities:
        print(f"\n   First week priorities:")
        for p in priorities:
            print(f"   • {p}")
    print(f"{'='*60}\n")
    print(f"Welcome message sent to Telegram chat {args.manager_chat_id}")


if __name__ == "__main__":
    asyncio.run(main())
