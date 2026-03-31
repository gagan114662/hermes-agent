#!/usr/bin/env python3
"""
Register daily customer acquisition cron jobs in Hermes.

Run once to set up:
    python scripts/setup_acquisition_crons.py

Creates 3 cron job files in ~/.hermes/cron/:
  1. daily-prospect-research (8am): research Reddit, Indeed, Maps
  2. daily-prospect-digest (9am): send batch to owner for approval
  3. weekly-content-post (Monday 10am): post inbound content to Reddit
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

CRON_DIR = Path.home() / ".hermes" / "cron"


def _now():
    return datetime.now(timezone.utc).isoformat()


def register_cron(name: str, schedule: str, prompt: str, skills: list) -> str:
    """Write a cron job JSON file to ~/.hermes/cron/. Returns file path."""
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())[:12]
    job = {
        "id": job_id,
        "name": name,
        "schedule": schedule,
        "prompt": prompt,
        "skills": skills,
        "enabled": True,
        "created_at": _now(),
    }
    job_file = CRON_DIR / f"{name}.json"
    job_file.write_text(json.dumps(job, indent=2))
    return str(job_file)


def main():
    jobs = [
        {
            "name": "daily-prospect-research",
            "schedule": "0 8 * * *",
            "prompt": (
                "Run daily prospect research using the customer-acquisition skill.\n"
                "Search Indeed, Reddit, and Google Maps for small business owners who need an AI employee.\n"
                "Add each scored prospect using prospect_add.\n"
                "Target: 10+ new prospects before the 9am digest."
            ),
            "skills": ["customer-acquisition"],
        },
        {
            "name": "daily-prospect-digest",
            "schedule": "0 9 * * *",
            "prompt": (
                "Generate and send the daily prospect digest to the owner.\n"
                "1. Call prospect_digest() to get top 10 new prospects\n"
                "2. Send via send_message to Telegram\n"
                "When owner replies APPROVE ALL: send outreach to all prospects.\n"
                "When owner replies REJECT N: skip those numbers, contact the rest."
            ),
            "skills": ["customer-acquisition"],
        },
        {
            "name": "weekly-content-post",
            "schedule": "0 10 * * 1",
            "prompt": (
                "Post weekly inbound content using the customer-acquisition skill.\n"
                "Draft and post to r/entrepreneur or r/smallbusiness:\n"
                "'I built an AI employee that handles calls+SMS for $299/mo.\n"
                " Drop your number below and it will call you in 60 seconds to demo itself.'\n"
                "Track any replies as prospects with prospect_add(source='reddit_inbound')."
            ),
            "skills": ["customer-acquisition"],
        },
    ]

    print(f"Registering {len(jobs)} acquisition cron jobs in {CRON_DIR}...")
    for job in jobs:
        path = register_cron(**job)
        print(f"  ✅ {job['name']} ({job['schedule']}) → {path}")

    print("\n🎯 All acquisition crons registered.")
    print("Verify: ls ~/.hermes/cron/")


if __name__ == "__main__":
    main()
