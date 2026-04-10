---
name: onboarding-333
description: >-
  3-3-3 onboarding scaffold — detects where a user is in their Hermes
  journey (day-1 / week-2 / month-2+) and routes them to the right
  next command: /specnew → /skillnew+/skilltest → /costmap+/lineage.
version: 1.0.0
author: hermes-core
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [Onboarding, Getting Started, Journey, Guidance]
    category: productivity
---

# 3-3-3 Onboarding Skill

## Overview

The 3-3-3 skill watches how many sessions a user has had with Hermes and
surfaces the single most valuable next action for where they are right now.

```
Stage 1 — day-1       (sessions 1–3)    → /specnew
Stage 2 — week-2      (sessions 4–14)   → /skillnew  /skilltest
Stage 3 — month-2+    (sessions 15+)    → /costmap   /lineage
```

It records one session bump per CLI startup and persists the counter to
`~/.hermes/onboarding.json`.

## When to Use

Use this skill when:
- The user types `/onboard` with no arguments
- The user asks "where do I start?", "what should I do next?",
  "how do I get the most out of Hermes?", or similar orientation questions
- A new session starts and the session count is ≤ 3 (surface a brief tip
  unprompted — one sentence max, then stop)

Do **not** use this skill for general Q&A or when the user has a specific
task in mind.

## Command Reference

| Command | Behaviour |
|---|---|
| `/onboard` | Show current stage, tip, and next command |
| `/onboard status` | Same as above — explicit status view |
| `/onboard reset` | Wipe the counter and start fresh (requires confirmation) |
| `/onboard debug` | Show raw `~/.hermes/onboarding.json` state |

## Stage Descriptions

### Stage 1 — day-1 (sessions 1–3)

The user hasn't built a context library yet.  Without it every session
starts cold.  The highest-leverage action is always `/specnew`.

**What to say:**
> "You're on session N.  The single highest-leverage thing you can do
> right now is run `/specnew <what you want to build>`.  It generates a
> precise spec and context library that Hermes loads every session —
> think of it as teaching Hermes your codebase once so you never have
> to re-explain it."

If the user asks follow-up questions about `/specnew`, run it for them
directly rather than explaining further.

### Stage 2 — week-2 (sessions 4–14)

The user has a spec and is running recurring workflows.  The highest-
leverage action is automating those workflows into reusable skills.

**What to say:**
> "You're on session N (week-2 stage).  Time to automate your patterns.
> Pick one thing you keep asking Hermes to do and run `/skillnew` to
> package it as a skill.  Then run `/skilltest` on the result — it runs
> a 5-test protocol (happy path, edge cases, negative cases) so you can
> trust it in production."

Show the user how to run `/skillnew <description>` if they're unsure.

### Stage 3 — month-2+ (sessions 15+)

The user is running complex delegations and cares about cost and
auditability.  Surface the control-plane tools.

**What to say:**
> "You're on session N (power-user stage).  Two tools worth knowing:
> `/costmap` shows the token spend per sub-task after every `/task` call,
> so you can spot which delegation is burning money.  `/lineage <file>`
> tells you exactly which agent goal wrote any file in your project."

## Unprompted Tips (session ≤ 3)

When the CLI starts a new session and the session count is 1, 2, or 3,
emit a single-line nudge at the bottom of the welcome banner:

```
💡 Tip: Run /specnew <what to build> to give Hermes permanent context
        for your project.  (Session 2 of 3 in the getting-started stage.)
```

Keep the nudge to ≤ 2 lines.  Never repeat the same tip twice in a row.
Stop showing unprompted tips after session 3.

## Reset Flow

When the user runs `/onboard reset`:
1. Print: "This will reset your onboarding counter to 0.  Type **yes** to confirm."
2. Wait for `yes`.
3. Call `reset_onboarding()` from `agent.onboarding`.
4. Print: "Counter reset.  You're back at session 0 / day-1 stage."

## Implementation Notes

- Session counting lives in `agent/onboarding.py` — `record_session()`,
  `get_journey_stage()`, `get_onboarding_state()`, `reset_onboarding()`
- The `/onboard` slash command is registered in `hermes_cli/commands.py`
  and dispatched from `cli.py → _show_onboard()`
- `record_session()` is called once per CLI startup in
  `cli.py → _post_init_hooks()` (after the agent is ready, not at import)
- Never call `record_session()` more than once per process lifetime
