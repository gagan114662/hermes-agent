# Daily Task Prep

Automated skill that runs at 2am Pacific to prepare the day's task list. Merges calendar events, recurring tasks, and due-today backlog items into `~/.hermes/workspace/tasks/current.md`.

## When to Use

- Triggered automatically at 2am Pacific via cron
- Or manually: "prep today's tasks" / "set up my day"

## What You Have Access To

- `calendar_list` — Google Calendar events for today
- `read_file` / `write_file` / `patch` — Task file manipulation
- `send_message` — Telegram notification to Gagan (chat_id: 8444910202)

## Process

### Step 1 — Read the current task file
```
read_file("~/.hermes/workspace/tasks/current.md")
```

### Step 2 — Pull today's calendar
```
calendar_list(days=1)
```
Filter out:
- Personal/family-only appointments (unless Gagan explicitly requested inclusion)
- Events on other people's calendars Gagan is only observing

### Step 3 — Identify due-today items
From the "Backlog with due date" section, find items with `due: TODAY_DATE`.

### Step 4 — Identify recurring tasks
- On weekdays: include all "Every weekday" items
- On weekends: skip unless Gagan requested them
- Check "Recurring reminders" for today's occurrences

### Step 5 — Merge into "Today" section

Rules:
- **Non-destructive**: preserve manually-added tasks and manual prioritization
- **Deduplicate**: normalize text and skip exact/near-exact duplicates already in "Today"
- **Order**: P1 items → due-today backlog → recurring tasks → calendar meetings (time-ordered)
- Format calendar events as: `[ ] [HH:MM PT] Meeting: <event title>`
- Move due-today backlog items from "Backlog" to "Today" (remove from Backlog)

### Step 6 — Write the updated file
Use `patch` for surgical edits. If structure has drifted, use `write_file` to rewrite cleanly.

### Step 7 — Notify Gagan
Send a brief Telegram message only if there are ≥1 items in Today:
```
📋 Day prepped: N tasks today (HH:MM first meeting / no meetings)
```
If no changes needed (Today already populated, no new items), stay silent — no edit, no message.

## Timezone

All times in America/Vancouver (Pacific). Date is YYYY-MM-DD.

## Example Output Message

```
📋 Day prepped: 4 tasks today (10:00 PT investor call, 2:00 PT team sync)
```
