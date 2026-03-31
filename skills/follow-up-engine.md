# Follow-Up Engine

## When to Use

Activate this skill when:
- User says "who needs a follow-up", "any leads going cold", "check on pending items"
- User says "nudge them", "send a reminder", "chase this down"
- Scheduled periodic scan (run every 6 hours via cron)
- After inbox triage identifies items needing follow-up
- After a meeting where action items were assigned to external parties
- When a CRM deal hasn't moved stages in more than 5 days
- When a customer hasn't responded in more than 7 days

## What You Need

### Tools
- `prospect_tool` — CRM: search leads, check deal stages, last contact dates, pipeline status
- `email_read` — Scan sent folder for unanswered emails, scan inbox for pending requests
- `email_send` — Send follow-up emails and nudges
- `send_message` — Telegram: notify owner of stalled items, send nudges to contacts on Telegram
- `sms_send` — Twilio: send SMS nudges for high-priority items when email isn't working
- `web_search` — Research context before sending nudges (news about contact's company, etc.)
- `state_db` — Track follow-up history, snooze dates, nudge count, promise registry
- `calendar_read` — Check for meetings that lacked follow-ups

### Data Needed
- CRM pipeline with deal stages and last-activity timestamps
- Sent email history (to detect unanswered outreach)
- Promise registry: commitments made by owner or others with deadlines
- Contact preferences: how each person prefers to be reached (email/Telegram/SMS/phone)
- Nudge templates per relationship type and urgency level

## Process

### Step 1: Scan All Sources for Stalled Items

Run a comprehensive scan across every system.

```
1. CRM PIPELINE SCAN:
   prospect_tool(action="list", filter="last_activity > 5 days ago")
   prospect_tool(action="list", filter="stage=proposal_sent AND days_in_stage > 3")
   prospect_tool(action="list", filter="stage=demo_scheduled AND date < today")

   Flag:
   - Leads with no activity in 5+ days
   - Proposals sent but not responded to in 3+ days
   - Demos that happened but no follow-up was sent
   - Deals stuck in same stage for >7 days
   - Trials expiring within 3 days with no conversion signal

2. UNANSWERED EMAILS:
   email_read(folder="SENT", after=7_days_ago)
   For each sent email, check if a reply exists:
     email_read(folder="INBOX", search=f"from:{recipient} subject:{thread_subject}")

   Flag:
   - Sent emails with no reply after 48 hours
   - Questions asked to owner by others with no response (owner's fault)
   - Threads that went dead mid-conversation

3. PROMISE REGISTRY:
   state_db(action="get_promises", status="open")

   Flag:
   - Promises made by owner that are overdue
   - Promises made by others to owner that are overdue
   - Commitments from meetings with no evidence of completion

4. CUSTOMER HEALTH:
   prospect_tool(action="list", filter="customer_type=active AND last_contact > 14 days")

   Flag:
   - Active customers with no touchpoint in 14+ days
   - Customers whose usage has dropped (if usage data available)
   - Customers approaching renewal with no recent engagement

5. TASK/APPROVAL SCAN:
   state_db(action="get_tasks", status="pending", assigned_to="others")

   Flag:
   - Tasks assigned to team members that are overdue
   - Approvals requested but not granted
   - Blockers waiting on external parties
```

### Step 2: Prioritize and Categorize

Sort all flagged items into priority tiers.

```
PRIORITY 1 — REVENUE AT RISK (act within 2 hours)
  - Hot lead going cold (proposal sent, no reply in 3+ days)
  - Active customer gone quiet during renewal window
  - Payment failed or billing issue unresolved
  - Trial expiring in <48 hours with engaged user

PRIORITY 2 — RELATIONSHIP MAINTENANCE (act within 24 hours)
  - Unanswered email from known contact (2+ days)
  - Meeting follow-up not sent (1+ day after meeting)
  - Warm intro received but not acted on
  - Promise made by owner, deadline approaching

PRIORITY 3 — PIPELINE HYGIENE (act within 48 hours)
  - Deal stuck in same stage for 7+ days
  - Lead with no activity in 5+ days
  - Overdue tasks assigned to team members
  - Customer last contacted 14+ days ago

PRIORITY 4 — OPTIONAL TOUCHPOINTS (weekly batch)
  - Industry contacts worth staying in touch with
  - Past customers who might re-engage
  - Conference contacts from recent events
  - Dormant partnerships worth reviving
```

### Step 3: Draft Nudges

For each item, compose an appropriate follow-up.

```
NUDGE RULES:
  1. FIRST nudge (48-72 hours): Light, friendly, adds value
     "Hey {name}, following up on this. Also noticed {relevant_news/value_add}."

  2. SECOND nudge (5-7 days): Direct, asks for status
     "Hi {name}, wanted to check if you had a chance to review. Happy to jump on a quick call if easier."

  3. THIRD nudge (10-14 days): Final, creates soft urgency
     "Hi {name}, circling back one last time. If timing isn't right, no worries — just let me know
      and I'll follow up next quarter."

  4. After 3 nudges: Mark as "cold" in CRM, stop automated follow-up

NUDGE CUSTOMIZATION BY RELATIONSHIP:
  - Customer (active): Warm, service-oriented. "Want to make sure you're set."
  - Lead (warm): Value-first. Include a relevant insight or resource.
  - Lead (cold): Brief, no-pressure. Easy opt-out.
  - Partner/investor: Professional, respectful of time. Never pushy.
  - Internal team: Direct, specific ask. "Can you update on X by EOD?"

CHANNEL SELECTION:
  - Default: Same channel as original conversation
  - If email unanswered after 2 nudges: Try Telegram or SMS
  - If internal team: Slack or Telegram (faster response)
  - For high-priority: Multi-channel (email + Telegram ping to owner)
```

**Nudge draft process:**

```
For each follow-up item:
  1. Check nudge history:
     state_db(action="get_nudge_count", contact=contact_id, thread=thread_id)

  2. Research fresh context to add value:
     web_search(query=f"{contact_company} recent news")
     → If anything relevant found, weave it into the nudge

  3. Draft message based on nudge number and relationship type

  4. Select channel based on contact preference and previous response pattern

  5. Queue for sending (immediate for P1, batched for P2-P4)
```

### Step 4: Execute Follow-Ups

```
FOR PRIORITY 1 (immediate):
  1. Send nudge via appropriate channel:
     email_send(to=contact, subject=thread_subject, body=nudge_text)
     OR send_message(chat_id=contact_telegram, text=nudge_text)
     OR sms_send(to=contact_phone, body=nudge_text)

  2. Notify owner:
     send_message(chat_id=owner_id, text=
       "FOLLOW-UP ALERT: {contact} hasn't responded to proposal (3 days).
        Sent nudge via email. Revenue at risk: ${deal_value}.")

  3. Log action:
     state_db(action="log_nudge", contact=contact_id, channel=channel,
       nudge_number=N, message=nudge_text)

FOR PRIORITY 2-3 (batched):
  1. Compile all nudges into a batch
  2. Present to owner for review:
     send_message(chat_id=owner_id, text=
       "FOLLOW-UP BATCH: 8 nudges ready to send.
        P2: 3 items (unanswered emails, meeting follow-ups)
        P3: 5 items (stalled deals, overdue tasks)
        Reply 'send all' or review individually.")

  3. On approval, send all and log

FOR PRIORITY 4 (weekly):
  1. Compile into weekly touchpoint list
  2. Include in weekly briefing
  3. Owner picks which to send
```

### Step 5: Track Outcomes

```
After each nudge:
  1. Set response check timer:
     state_db(action="set_check", contact=contact_id,
       check_date=today+48h, expected="reply")

  2. When response comes in:
     - Update CRM: prospect_tool(action="update", id=contact_id, last_activity=now)
     - Move deal stage if appropriate
     - Clear from follow-up queue
     - Log response time for future pattern analysis

  3. When no response after final nudge:
     - Mark contact as "cold" in CRM
     - Remove from active follow-up
     - Set 90-day re-engagement reminder
     - Notify owner: "{contact} unresponsive after 3 nudges. Moved to cold."
```

## Output Format

### Follow-Up Scan Report

```
FOLLOW-UP ENGINE — {date} {time}
====================================

REVENUE AT RISK (P1) — Act now
  1. James Wu (TechStart Inc) — Proposal sent 4 days ago, $24K deal
     Last contact: email, March 26. No reply.
     Nudge #1 sent via email. Added note about their recent product launch.
     → Owner notified via Telegram

  2. Trial expiring: maria@designco.io — 36 hours remaining
     Usage: Active (logged in 12 times). Has not upgraded.
     → Sent personalized upgrade email with 20% extension offer.

NEEDS YOUR INPUT (P2) — Today
  3. Sarah Chen (Acme) — Waiting for API timeline from you (3 days)
     → Draft reply ready. Approve in inbox triage.

  4. Meeting follow-up not sent: VC call from yesterday
     → Draft follow-up ready. Review and send.

PIPELINE HYGIENE (P3) — This week
  5. 4 deals stuck >7 days: [Deal A, B, C, D]
     → Nudges drafted for each. Reply 'send all' to batch.

  6. 2 overdue team tasks: [Task X assigned to Dev, Task Y to Marketing]
     → Sent reminders via Slack.

WEEKLY TOUCHPOINTS (P4)
  7. 3 contacts worth re-engaging: [past customer, conference contact, advisor]
     → Drafts available in weekly briefing.

STATS:
  Items scanned: 142
  Follow-ups needed: 12
  Auto-sent: 4 (P1 items)
  Queued for review: 8
  Response rate (last 30 days): 67%
```

### Individual Nudge Draft

```
TO: james.wu@techstart.io
RE: TechStart + Hermes — Implementation Proposal
NUDGE #: 1 of 3
CHANNEL: Email (original channel)

Hi James,

Following up on the proposal I sent last week. I saw TechStart
just launched the new analytics dashboard — congrats, it looks great.

Happy to jump on a 15-minute call to walk through the implementation
timeline if that's easier than async. What does Thursday look like?

Best,
{Owner}

[APPROVE] [EDIT] [SKIP] [CALL INSTEAD]
```

## Examples

### Example 1: Periodic Scan (Cron)

**Input:** (Automatic, every 6 hours)

**Process:**
1. Scan CRM: 3 deals stalled, 1 trial expiring
2. Scan email: 5 unanswered, 2 meeting follow-ups missing
3. Scan promises: 1 overdue commitment by owner
4. Prioritize: 2 P1, 3 P2, 4 P3, 2 P4
5. Auto-send P1 nudges, queue P2-P4 for review

**Output:** Scan report sent to owner via Telegram with action items

### Example 2: Manual Follow-Up Request

**Input:** "Nudge the Acme team about the contract"

**Process:**
1. Look up Acme in CRM: Sarah Chen (primary), James Liu (CTO)
2. Check last contact: email 5 days ago about contract terms
3. Check nudge history: no previous nudges on this thread
4. Research: Acme raised Series C last week (good conversation hook)
5. Draft nudge #1 with funding congrats + contract reminder

**Output:** Draft nudge for review, sent via email to Sarah with CC to James

### Example 3: "Who's going cold?"

**Input:** "Who's going cold in the pipeline?"

**Process:**
1. Pull all active deals from CRM
2. Sort by days since last activity
3. Cross-reference with email for any unreported contact
4. Flag deals with decreasing engagement

**Output:**
```
GOING COLD (sorted by risk):
  1. James Wu (TechStart) — 4 days silent after proposal. $24K.
  2. Design Co trial — expiring in 36 hours. Active user, no upgrade.
  3. Mike Torres (Consulting firm) — 8 days since demo. $12K.
  4. Legacy customer (BrightPath) — 18 days since last login. Churn risk.

Nudges drafted for all 4. Send now?
```
