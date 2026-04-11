#!/usr/bin/env python3
"""
Hermes Tenant Management CLI

Usage:
    python scale/tenant_cli.py add "Restaurant Mario" --telegram-token 7123456:AAF...
    python scale/tenant_cli.py add "Pizza Palace" --telegram-token 7999:BBG... --model openrouter/anthropic/claude-sonnet-4
    python scale/tenant_cli.py list
    python scale/tenant_cli.py info restaurant-mario
    python scale/tenant_cli.py memory restaurant-mario --set "Hours: Mon-Fri 11am-10pm, Sat-Sun 12pm-11pm"
    python scale/tenant_cli.py memory restaurant-mario --type menu --set "Pizza Margherita $12, Pasta Carbonara $15..."
    python scale/tenant_cli.py memory restaurant-mario --show
    python scale/tenant_cli.py disable restaurant-mario
    python scale/tenant_cli.py enable restaurant-mario
    python scale/tenant_cli.py stats restaurant-mario

Env vars:
    DATABASE_URL   postgresql://hermes:pass@localhost:5432/hermes
"""

import argparse
import asyncio
import os
import re
import sys
import uuid
from datetime import datetime

import asyncpg


async def get_db():
    url = os.getenv("DATABASE_URL", "postgresql://hermes:hermes@localhost:5432/hermes")
    return await asyncpg.connect(url)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_add(args):
    db = await get_db()
    slug = slugify(args.name)

    # Check if slug already exists
    existing = await db.fetchrow("SELECT id FROM tenants WHERE slug = $1", slug)
    if existing:
        print(f"Error: Tenant '{slug}' already exists (id: {existing['id']})")
        await db.close()
        return

    api_key = args.api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: No API key provided. Use --api-key or set OPENROUTER_API_KEY")
        await db.close()
        return

    tenant_id = uuid.uuid4()
    model = args.model or "openrouter/google/gemini-2.5-flash-preview"

    await db.execute("""
        INSERT INTO tenants (id, name, slug, model, api_key_encrypted)
        VALUES ($1, $2, $3, $4, $5)
    """, tenant_id, args.name, slug, model, api_key)

    if args.telegram_token:
        await db.execute("""
            INSERT INTO tenant_platforms (tenant_id, platform, bot_token)
            VALUES ($1, 'telegram', $2)
        """, tenant_id, args.telegram_token)

    print(f"  Tenant added: {args.name}")
    print(f"  Slug:     {slug}")
    print(f"  ID:       {tenant_id}")
    print(f"  Model:    {model}")
    if args.telegram_token:
        print(f"  Telegram: connected")
    print()
    print(f"  Next steps:")
    print(f"  1. Add business info:")
    print(f"     python scale/tenant_cli.py memory {slug} --set 'Your business description here'")
    print(f"  2. Add menu/services:")
    print(f"     python scale/tenant_cli.py memory {slug} --type menu --set 'Item 1 $10, Item 2 $15...'")
    print(f"  3. Restart gateway to pick up new bot")

    await db.close()


async def cmd_list(args):
    db = await get_db()
    rows = await db.fetch("""
        SELECT t.*, count(tp.id) as platforms,
               (SELECT count(*) FROM sessions s WHERE s.tenant_id = t.id) as sessions,
               (SELECT count(*) FROM message_log m WHERE m.tenant_id = t.id) as messages
        FROM tenants t
        LEFT JOIN tenant_platforms tp ON tp.tenant_id = t.id
        GROUP BY t.id
        ORDER BY t.created_at
    """)

    if not rows:
        print("  No tenants yet. Add one with:")
        print("  python scale/tenant_cli.py add 'Business Name' --telegram-token TOKEN")
        await db.close()
        return

    print(f"\n  {'Slug':<25} {'Status':<10} {'Model':<40} {'Sessions':<10} {'Messages':<10}")
    print(f"  {'─' * 25} {'─' * 10} {'─' * 40} {'─' * 10} {'─' * 10}")
    for r in rows:
        status = "active" if r["active"] else "disabled"
        model_short = (r["model"] or "default")[-38:]
        print(f"  {r['slug']:<25} {status:<10} {model_short:<40} {r['sessions']:<10} {r['messages']:<10}")
    print()
    await db.close()


async def cmd_info(args):
    db = await get_db()
    tenant = await db.fetchrow("SELECT * FROM tenants WHERE slug = $1", args.slug)
    if not tenant:
        print(f"  Tenant '{args.slug}' not found")
        await db.close()
        return

    platforms = await db.fetch(
        "SELECT * FROM tenant_platforms WHERE tenant_id = $1", tenant["id"]
    )
    memories = await db.fetch(
        "SELECT * FROM tenant_memory WHERE tenant_id = $1", tenant["id"]
    )

    print(f"\n  Tenant: {tenant['name']}")
    print(f"  Slug:   {tenant['slug']}")
    print(f"  ID:     {tenant['id']}")
    print(f"  Status: {'active' if tenant['active'] else 'disabled'}")
    print(f"  Model:  {tenant['model']}")
    print(f"  Rate:   {tenant['rate_limit_per_minute']}/min (burst: {tenant['rate_limit_burst']})")
    print(f"  Created: {tenant['created_at'].strftime('%Y-%m-%d %H:%M')}")

    print(f"\n  Platforms:")
    for p in platforms:
        status = "enabled" if p["enabled"] else "disabled"
        token_preview = p["bot_token"][:10] + "..." if p["bot_token"] else "none"
        print(f"    {p['platform']}: {token_preview} [{status}]")

    print(f"\n  Memory ({len(memories)} entries):")
    for m in memories:
        preview = m["content"][:80].replace("\n", " ")
        print(f"    [{m['memory_type']}] {preview}...")

    print()
    await db.close()


async def cmd_memory(args):
    db = await get_db()
    tenant = await db.fetchrow("SELECT id, name FROM tenants WHERE slug = $1", args.slug)
    if not tenant:
        print(f"  Tenant '{args.slug}' not found")
        await db.close()
        return

    if args.show:
        memories = await db.fetch(
            "SELECT * FROM tenant_memory WHERE tenant_id = $1 ORDER BY memory_type",
            tenant["id"],
        )
        if not memories:
            print(f"  No memory set for {tenant['name']}")
        for m in memories:
            print(f"\n  [{m['memory_type']}]")
            print(f"  {m['content']}")
        print()
        await db.close()
        return

    if args.set:
        mem_type = args.type or "business_info"

        # Read from file if path provided
        content = args.set
        if os.path.isfile(content):
            with open(content, "r") as f:
                content = f.read()

        await db.execute("""
            INSERT INTO tenant_memory (tenant_id, memory_type, content, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (tenant_id, memory_type) DO UPDATE SET
                content = $3, updated_at = now()
        """, tenant["id"], mem_type, content)

        # Clear cached system prompts so they rebuild
        await db.execute("""
            UPDATE sessions SET system_prompt = NULL WHERE tenant_id = $1
        """, tenant["id"])

        print(f"  Memory [{mem_type}] updated for {tenant['name']}")
        print(f"  ({len(content)} chars, system prompts cleared for rebuild)")
        await db.close()
        return

    if args.delete:
        mem_type = args.delete
        await db.execute("""
            DELETE FROM tenant_memory WHERE tenant_id = $1 AND memory_type = $2
        """, tenant["id"], mem_type)
        await db.execute("""
            UPDATE sessions SET system_prompt = NULL WHERE tenant_id = $1
        """, tenant["id"])
        print(f"  Memory [{mem_type}] deleted for {tenant['name']}")
        await db.close()
        return

    print("  Use --set 'content' or --show or --delete type_name")
    await db.close()


async def cmd_prompt(args):
    db = await get_db()
    tenant = await db.fetchrow("SELECT id, name FROM tenants WHERE slug = $1", args.slug)
    if not tenant:
        print(f"  Tenant '{args.slug}' not found")
        await db.close()
        return

    if args.set:
        await db.execute(
            "UPDATE tenants SET system_prompt_template = $1 WHERE id = $2",
            args.set, tenant["id"],
        )
        # Clear cached prompts so sessions rebuild
        await db.execute("UPDATE sessions SET system_prompt = NULL WHERE tenant_id = $1", tenant["id"])
        print(f"  System prompt updated for {tenant['name']}")
        print(f"  ({len(args.set)} chars, sessions cleared for rebuild)")
    else:
        row = await db.fetchrow("SELECT system_prompt_template FROM tenants WHERE id = $1", tenant["id"])
        tmpl = row["system_prompt_template"]
        if tmpl:
            print(f"\n  System prompt for {tenant['name']}:\n")
            print(f"  {tmpl}\n")
        else:
            print(f"  No custom system prompt set — using default.")
    await db.close()


async def cmd_tools(args):
    db = await get_db()
    tenant = await db.fetchrow("SELECT id, name FROM tenants WHERE slug = $1", args.slug)
    if not tenant:
        print(f"  Tenant '{args.slug}' not found")
        await db.close()
        return

    if args.set:
        toolsets = args.set  # list of strings from nargs='+'
        await db.execute(
            "UPDATE tenants SET enabled_toolsets = $1 WHERE id = $2",
            toolsets, tenant["id"],
        )
        print(f"  Tools updated for {tenant['name']}: {', '.join(toolsets)}")
    elif args.show:
        row = await db.fetchrow("SELECT enabled_toolsets FROM tenants WHERE id = $1", tenant["id"])
        toolsets = row["enabled_toolsets"] or []
        print(f"\n  Enabled toolsets for {tenant['name']}:")
        for t in toolsets:
            print(f"    - {t}")
        print()
    else:
        print("  Use --set tool1 tool2 ... or --show")
    await db.close()


async def cmd_disable(args):
    db = await get_db()
    result = await db.execute("UPDATE tenants SET active = false WHERE slug = $1", args.slug)
    if "UPDATE 1" in result:
        print(f"  Tenant '{args.slug}' disabled")
    else:
        print(f"  Tenant '{args.slug}' not found")
    await db.close()


async def cmd_enable(args):
    db = await get_db()
    result = await db.execute("UPDATE tenants SET active = true WHERE slug = $1", args.slug)
    if "UPDATE 1" in result:
        print(f"  Tenant '{args.slug}' enabled (restart gateway to start polling)")
    else:
        print(f"  Tenant '{args.slug}' not found")
    await db.close()


async def cmd_stats(args):
    db = await get_db()
    tenant = await db.fetchrow("SELECT id, name FROM tenants WHERE slug = $1", args.slug)
    if not tenant:
        print(f"  Tenant '{args.slug}' not found")
        await db.close()
        return

    counts = await db.fetchrow("""
        SELECT
            count(*) as total,
            count(*) FILTER (WHERE created_at > now() - interval '24 hours') as last_24h,
            count(*) FILTER (WHERE created_at > now() - interval '7 days') as last_7d,
            sum(input_tokens) as input_tokens,
            sum(output_tokens) as output_tokens,
            sum(cost_usd) as total_cost,
            avg(duration_ms) as avg_duration,
            max(created_at) as last_message
        FROM message_log WHERE tenant_id = $1
    """, tenant["id"])

    sessions = await db.fetchval("SELECT count(*) FROM sessions WHERE tenant_id = $1", tenant["id"])

    print(f"\n  Stats for {tenant['name']}:")
    print(f"  Sessions:        {sessions}")
    print(f"  Total messages:  {counts['total']}")
    print(f"  Last 24h:        {counts['last_24h']}")
    print(f"  Last 7 days:     {counts['last_7d']}")
    print(f"  Input tokens:    {counts['input_tokens'] or 0:,}")
    print(f"  Output tokens:   {counts['output_tokens'] or 0:,}")
    print(f"  Total cost:      ${float(counts['total_cost'] or 0):.4f}")
    print(f"  Avg response:    {float(counts['avg_duration'] or 0):.0f}ms")
    if counts["last_message"]:
        print(f"  Last message:    {counts['last_message'].strftime('%Y-%m-%d %H:%M')}")
    print()
    await db.close()


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Hermes Tenant Management")
    subs = parser.add_subparsers(dest="command")

    # add
    p_add = subs.add_parser("add", help="Add a new tenant")
    p_add.add_argument("name", help="Business name")
    p_add.add_argument("--telegram-token", help="Telegram bot token")
    p_add.add_argument("--api-key", help="OpenRouter API key (or set OPENROUTER_API_KEY)")
    p_add.add_argument("--model", help="LLM model (default: gemini-2.5-flash)")

    # list
    subs.add_parser("list", help="List all tenants")

    # info
    p_info = subs.add_parser("info", help="Show tenant details")
    p_info.add_argument("slug", help="Tenant slug")

    # memory
    p_mem = subs.add_parser("memory", help="Manage tenant memory/knowledge")
    p_mem.add_argument("slug", help="Tenant slug")
    p_mem.add_argument("--set", help="Set memory content (text or file path)")
    p_mem.add_argument("--type", help="Memory type (default: business_info)")
    p_mem.add_argument("--show", action="store_true", help="Show all memory")
    p_mem.add_argument("--delete", help="Delete a memory type")

    # prompt
    p_prompt = subs.add_parser("prompt", help="Get/set custom system prompt")
    p_prompt.add_argument("slug", help="Tenant slug")
    p_prompt.add_argument("--set", help="System prompt text")

    # tools
    p_tools = subs.add_parser("tools", help="Get/set enabled toolsets")
    p_tools.add_argument("slug", help="Tenant slug")
    p_tools.add_argument("--set", nargs="+", help="List of toolsets to enable")
    p_tools.add_argument("--show", action="store_true", help="Show current toolsets")

    # disable / enable
    p_dis = subs.add_parser("disable", help="Disable a tenant")
    p_dis.add_argument("slug")
    p_en = subs.add_parser("enable", help="Enable a tenant")
    p_en.add_argument("slug")

    # stats
    p_stats = subs.add_parser("stats", help="Show tenant message stats")
    p_stats.add_argument("slug")

    args = parser.parse_args()

    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "info": cmd_info,
        "memory": cmd_memory,
        "prompt": cmd_prompt,
        "tools": cmd_tools,
        "disable": cmd_disable,
        "enable": cmd_enable,
        "stats": cmd_stats,
    }

    if args.command in commands:
        asyncio.run(commands[args.command](args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
