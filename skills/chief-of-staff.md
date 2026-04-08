# Personal Chief of Staff Mode

## When to Use

Activate this skill when:
- Scheduled morning briefing (cron: daily at 7:00am owner's timezone)
- User says "brief me", "what's the situation", "morning update", "what do I need to know"
- User says "what should I focus on today", "daily digest", "start my day"
- End of day wrap-up requested: "wrap up my day", "EOD summary"
- User says "what did I miss" after being away
- Weekly reset requested: "plan my week", "weekly priorities"

## What You Need

### Tools
- `calendar_read` — Today's schedule, upcoming conflicts, meeting prep needs
- `email_read` — Unread count, urgent messages, pending threads
- `prospect_tool` — Pipeline health, deals at risk, customer alerts
- `state_db` — Overdue tasks, pending decisions, follow-up queue, KPI snapshots
- `send_message` — Deliver briefing via Telegram
- `email_send` — Deliver extended briefing via email if preferred
- `web_search` — Industry news, competitor moves, relevant headlines
- `browser_navigate` — Pull dashboard data for metrics section
- `file_tools` — Generate and store briefing archive

### Data Needed
- All data from subordinate skills: inbox-triage, calendar-intelligence, follow-up-engine, kpi-watcher, customer-support-ops
- Owner's current priorities and active projects
- Decision queue: decisions waiting for owner input
- Promise registry: commitments with deadlines approaching
- Team task status: what's blocked, what's overdue

## Process

### Step 1: Gather Intelligence (Run All Scans)

Execute data collection from every source in parallel.

```
PARALLEL SCAN — run all simultaneously:

1. CALENDAR SCAN:
   calendar_read(start=today, end=today+2d)
   → Today's meetings, tomorrow's prep needs
   → Conflicts detected
   → Focus time available
   → Meeting prep status (briefs ready or needed)

2. INBOX SCAN:
   email_read(folder="INBOX", status="UNSEEN")
   → Total unread count
   → Urgent messages (VIP senders, urgency keywords)
   → Messages waiting for owner's reply (older than 24h)

3. PIPELINE SCAN:
   prospect_tool(action="pipeline_summary")
   prospect_tool(action="list", filter="at_risk OR stalled")
   → Pipeline total value
   → Deals moving forward vs stalled
   → Leads going cold
   → Customers at churn risk

4. TASK SCAN:
   state_db(action="get_tasks", status="overdue OR due_today")
   state_db(action="get_decisions", status="pending")
   state_db(action="get_promises", status="open AND due_within_3d")
   → Overdue items
   → Decisions needing input
   → Promises approaching deadline

5. METRICS SCAN:
   state_db(action="get_latest_metrics")
   → Key numbers: MRR, signups, churn, support volume
   → Any active anomalies from kpi-watcher

6. SUPPORT SCAN:
   state_db(action="get_ticket_summary")
   → Open ticket count by priority
   → Escalations needing owner attention
   → Emerging patterns

7. NEWS SCAN:
   web_search(query=f"{industry} news today {competitors}")
   → Relevant industry developments
   → Competitor moves
   → Market events that affect business
```

### Step 2: Identify What Matters

Filter the noise. The briefing should highlight only what needs attention.

```
PRIORITY FILTER:

TIER 1 — ACT NOW (owner must handle today)
  - Overdue decisions that block others
  - Urgent customer escalation (enterprise, churn risk)
  - Calendar conflicts for today
  - Promises due today or overdue
  - Critical metric anomaly
  - Revenue at risk (deal expiring, payment failed)

TIER 2 — AWARENESS (owner should know but can delegate)
  - Pipeline health changes (deals stalled, new leads)
  - Support volume trends
  - Team member blocked on owner input
  - Meeting prep needed for tomorrow
  - Moderate metric changes

TIER 3 — CONTEXT (nice to know, include briefly)
  - Industry news that's relevant
  - Competitor activity
  - Positive signals (new signups, good reviews, deals advancing)
  - Weekly trend summaries

FILTERING RULES:
  - Maximum 5 items in Tier 1 (if more, sub-prioritize)
  - Maximum 5 items in Tier 2
  - Maximum 3 items in Tier 3
  - If everything is green, say so briefly — don't invent problems
  - Never include items the owner already addressed yesterday
```

### Step 3: Compose the Daily Briefing

Structure the briefing for fast scanning — owner should get the picture in 30 seconds.

```
BRIEFING STRUCTURE:

1. ONE-LINE STATUS
   A single sentence: How are things overall?
   "All clear — no fires. Focus day ahead."
   OR "Heads up — 2 items need you before noon."
   OR "Busy day — 5 meetings, 1 escalation, pipeline needs attention."

2. NEEDS YOUR INPUT (Tier 1)
   Numbered list of items only the owner can handle.
   Each item: what, why it matters, suggested action, deadline.

3. CALENDAR (today)
   Timeline view of the day with prep notes.
   Flag any conflicts or missing prep.

4. NUMBERS SNAPSHOT
   3-5 key metrics with direction arrows.
   Only highlight anomalies or meaningful changes.

5. PIPELINE & CUSTOMERS
   Deals moving, deals stuck, new leads, churn risks.
   One line per notable item.

6. WHAT I HANDLED
   Things the AI took care of overnight/since last briefing.
   Owner sees this to build trust and know what happened.

7. RECOMMENDED FOCUS
   "If you only do 3 things today, do these:"
   Based on impact, urgency, and what only the owner can do.

8. END WITH A QUESTION
   "What should I tackle first?" or "Anything to add to today's priorities?"
   This keeps the loop going.
```

### Step 4: Deliver the Briefing

```
PRIMARY CHANNEL: Telegram
  send_message(chat_id=owner_id, text=formatted_briefing)

  Telegram formatting:
  - Use bold for section headers
  - Use bullet points, not paragraphs
  - Keep total length under 2000 characters for mobile readability
  - If briefing is long, split: summary on Telegram, full version via email

BACKUP CHANNEL: Email
  If briefing exceeds Telegram length or contains tables/links:
  email_send(to=owner, subject=f"Daily Brief — {date}", body=full_briefing)
  send_message(chat_id=owner_id, text="Morning brief sent to email — 2 urgent items flagged.")

ARCHIVE:
  file_tools(action="write", path=f"briefings/{date}_morning.md", content=briefing)
  state_db(action="log_briefing", date=today, items=briefing_items)
```

### Step 5: End-of-Day Wrap-Up (if requested or scheduled)

```
EOD BRIEFING STRUCTURE:

1. WHAT GOT DONE TODAY
   - Meetings held: {count} — key outcomes
   - Emails sent/received: {count} — notable threads
   - Tickets resolved: {count}
   - Deals advanced: {list}

2. WHAT DIDN'T GET DONE
   - Items from morning brief that are still open
   - Why (blocked, deprioritized, ran out of time)
   - Carried forward to tomorrow

3. WHAT I DID WHILE YOU WORKED
   - Follow-ups sent automatically
   - Tickets handled without escalation
   - Metrics monitored — all normal (or flags)

4. TOMORROW PREVIEW
   - Calendar: {count} meetings, first at {time}
   - Deadlines: {list}
   - Prep needed: {what to review tonight}

5. OUTSTANDING ITEMS
   - Decisions still pending: {list}
   - People waiting on you: {list with days waiting}
```

### Step 6: Weekly Reset (Monday morning or on request)

```
WEEKLY BRIEFING — augments the daily brief with:

1. LAST WEEK SCORECARD
   - Goals set → goals achieved
   - Key wins
   - What slipped and why

2. THIS WEEK'S PRIORITIES
   - Top 3 must-do items (owner-level)
   - Delegated items to track
   - Upcoming deadlines

3. PIPELINE REVIEW
   - Week-over-week: new leads, closed deals, lost deals
   - Revenue forecast for the month
   - Deals to focus on this week

4. METRICS TREND
   - 4-week trends for key metrics
   - Trajectory toward monthly/quarterly goals

5. PEOPLE CHECK
   - Customers to reach out to
   - Team members to check in with
   - Network contacts to nurture

6. BLOCK YOUR CALENDAR
   - Suggest focus blocks for the week
   - Flag overloaded days
   - Recommend what to move or cancel
```

## Output Format

### Morning Briefing (Telegram)

```
MORNING BRIEF — {day_of_week}, {date}

Status: Moderate day — 3 meetings, 1 item needs you before noon.

NEEDS YOUR INPUT:
  1. Acme contract renewal — decision needed by EOD.
     Options memo ready (sent yesterday). Recommend: Option B.
  2. James Wu demo follow-up — he asked a pricing question
     only you can answer. Draft reply in your inbox.

TODAY'S CALENDAR:
  9:00  Focus block (protected)
  10:30 Team standup (15 min)
  11:00 Call with James Wu — brief ready
  2:00  Sarah Chen / Acme — brief ready, bring contract decision
  Rest of day: open for deep work

NUMBERS:
  MRR: $24,300 (+2.1% WoW)
  Signups yesterday: 12 (normal)
  Support: 3 open tickets (none critical)
  Pipeline: $89K total, 2 deals in negotiation

WHAT I HANDLED OVERNIGHT:
  - Triaged 18 emails (3 need your reply, 15 handled)
  - Sent follow-up nudges to 2 stalled leads
  - Resolved 2 support tickets (how-to questions)
  - Archived 11 spam/noise messages

TODAY'S FOCUS (my recommendation):
  1. Close the Acme renewal decision (highest revenue impact)
  2. Reply to James Wu before your 11am call
  3. Use afternoon focus block for the product roadmap doc

What should I tackle first?
```

### End-of-Day Wrap-Up

```
EOD WRAP — {date}

DONE TODAY:
  Meetings: 3 held (standup, James call, Acme sync)
  Emails: 8 sent, 22 received
  Decisions: Acme renewal — chose Option B, contract sent
  Pipeline: James Wu moved to negotiation stage ($24K)

STILL OPEN:
  - Product roadmap doc (deprioritized, moved to tomorrow)
  - 2 support tickets escalated (engineering working on fix)

I HANDLED:
  - 4 support tickets auto-resolved
  - 3 follow-up nudges sent (1 got a reply — DesignCo is back)
  - Meeting follow-up emails sent for all 3 meetings

TOMORROW:
  First meeting: 10am (team sync)
  Deadlines: Product roadmap draft, investor update prep
  Prep needed: Review Q1 metrics for investor deck

WAITING ON YOU (2 people):
  - Marketing lead: campaign approval (1 day)
  - Dev team: deploy go/no-go (since this afternoon)
```

## Examples

### Example 1: Calm Monday Morning

**Input:** (Automatic, 7:00am cron)

**Process:**
1. Scan all sources: no urgent items, light calendar, metrics stable
2. Pipeline: 1 new lead from weekend, no stalled deals
3. Support: 2 tickets, both low priority
4. No overdue decisions or promises

**Output:**
```
MORNING BRIEF — Monday, March 30

Status: Clean start to the week. No fires.

NEEDS YOUR INPUT:
  Nothing urgent. All clear.

TODAY: 2 meetings (10am standup, 2pm 1:1). Rest is focus time.
NUMBERS: All stable. MRR $24.3K, 8 signups over weekend.
OVERNIGHT: Handled 6 emails, resolved 2 support tickets.

WEEKLY PRIORITIES (my suggestion):
  1. Close TechStart deal ($24K) — proposal sent last week
  2. Prep investor update — meeting is Thursday
  3. Ship CSV export feature — 8 customer requests

What's your #1 priority this week?
```

### Example 2: Fire Drill Morning

**Input:** (Automatic, 7:00am cron — but issues detected)

**Process:**
1. Metrics: Revenue dropped 15% overnight (payment processor issue)
2. Support: 5 P1 tickets from enterprise customers
3. Pipeline: Acme renewal deadline is today, no decision made
4. Calendar: Triple-booked at 2pm

**Output:**
```
MORNING BRIEF — Tuesday, March 31

Status: 3 fires need attention before 10am.

URGENT:
  1. Revenue down 15% — Stripe webhook issue. 8 failed charges.
     Engineering notified. Need you to approve retry strategy.
  2. 5 enterprise customers reporting errors — related to Stripe issue.
     Drafts ready for all 5. Approve batch send?
  3. Acme renewal — DEADLINE TODAY. Decision memo in your inbox.
     Recommend: Option B (renew at $140K with API SLA addon).

CALENDAR CONFLICT:
  2:00pm — triple booked. Recommend: keep Acme call, move others.
  Alternatives proposed for the other 2 meetings.

[Full briefing sent to email with details]

What do you want me to handle first?
```

### Example 3: "What did I miss?"

**Input:** "I was offline for 2 days. What did I miss?"

**Process:**
1. Compile all activity from past 48 hours
2. Highlight decisions made on owner's behalf
3. Surface items that were deferred awaiting owner
4. Show metric changes over the period

**Output:** Extended briefing covering 2 days of activity, organized by priority, with clear action items for catching up.
