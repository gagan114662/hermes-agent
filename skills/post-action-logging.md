# Post-Action Logging

## When to Use

This skill runs AUTOMATICALLY after every significant action Hermes takes. It is not manually invoked — it's a background discipline that ensures accountability and enables retrospectives.

Trigger after:
- Email sent (outbound sales, follow-up, support reply)
- Social media post published
- Meeting scheduled or completed
- Deal stage changed in CRM
- Document created or sent (proposal, report, memo)
- Phone/voice call completed
- Browser automation task completed
- Cron job executed
- Growth engine campaign run
- Any task delegated to or completed for the owner
- Support ticket resolved or escalated
- Decision memo delivered
- KPI anomaly detected and reported
- Follow-up nudge sent

Also activate when user says:
- "What did you do", "show me the log", "audit trail", "action history"
- "Weekly summary", "what happened this week", "activity report"
- "Export actions for [period]" for investor updates or compliance

---

## What You Need

### Tools
- `state_db` — Primary log storage: write action records, query history, generate reports
- `prospect_tool` — Update CRM records with action outcomes, link actions to contacts/deals
- `file_tools` — Write detailed logs to disk, generate report files, export audit data
- `send_message` — Deliver summaries via Telegram
- `email_send` — Deliver weekly reports, share audit logs with stakeholders
- `calendar_read` — Correlate actions with calendar events for context

### Data Needed
- Action context: what skill triggered, what was the input, what was decided
- References: email IDs, ticket numbers, CRM record IDs, URLs involved
- Timestamps: start time, end time, duration
- Outcomes: success/failure, measurable result, follow-up needed
- Actor: which skill or human initiated the action

---

## Process

### Step 1: Capture the Action Record

Every action the agent takes MUST be logged immediately upon completion. Use this schema:

```json
{
  "id": "act_{uuid}",
  "timestamp": "2026-03-30T14:23:00Z",
  "skill": "follow-up-engine",
  "action_type": "nudge_sent",
  "summary": "Sent follow-up #2 to James Wu re: TechStart proposal",
  "detail": {
    "what": "Email follow-up nudge, second attempt",
    "why": "Proposal sent 5 days ago with no reply. Deal value $24K. Auto-triggered by follow-up engine scan.",
    "who": {
      "contact": "james.wu@techstart.io",
      "contact_name": "James Wu",
      "company": "TechStart Inc",
      "crm_id": "prospect_4821"
    },
    "how": {
      "channel": "email",
      "tool_used": "email_send",
      "template": "nudge_2_value_add",
      "content_preview": "Hi James, following up on the proposal..."
    }
  },
  "references": {
    "email_id": "msg_abc123",
    "thread_id": "thread_xyz",
    "crm_deal_id": "deal_789",
    "related_ticket": null,
    "urls": ["https://stripe.com/invoice/xyz"]
  },
  "outcome": {
    "status": "sent",
    "measurable_result": null,
    "error": null
  },
  "follow_up": {
    "needed": true,
    "date": "2026-04-02",
    "action": "Check if James replied. If not, send final nudge (#3).",
    "auto_scheduled": true
  },
  "metadata": {
    "duration_ms": 1240,
    "tokens_used": 850,
    "triggered_by": "cron_6h_scan",
    "parent_action": "act_parent_uuid",
    "session_id": "session_abc",
    "sensitivity": "normal"
  }
}
```

### Step 2: Write to All Relevant Stores

Log to multiple locations for redundancy and queryability.

```
1. PRIMARY LOG — State Database:
   state_db(action="log_action", data=action_record)

   The state_db is the source of truth. All queries go here.
   Index by: timestamp, skill, action_type, contact, outcome.status

2. CRM UPDATE — Link to contacts/deals:
   If action involves a contact:
     prospect_tool(action="add_activity", id=crm_id, data={
       type: action_type,
       description: summary,
       timestamp: timestamp,
       outcome: outcome.status,
       next_follow_up: follow_up.date
     })

   This ensures the CRM shows a complete timeline of all interactions,
   whether done by human or AI.

3. FILE LOG — Append to daily JSONL file:
   file_tools(action="append",
     path="~/.hermes/logs/actions/{date}.jsonl",
     content=json.dumps(action_record) + "\n"
   )

   JSONL format: one JSON object per line for easy parsing.
   Daily files keep sizes manageable. Always append, never overwrite.

4. AUDIT TRAIL — Human-readable, immutable:
   file_tools(action="append",
     path="~/.hermes/logs/audit/{year}-{month}.log",
     content="[{timestamp}] [{skill}] {summary} | outcome={outcome.status} | ref={references}\n"
   )

   Append-only. Never modify past entries.
```

### Step 3: Categorize Action Types

Maintain a consistent taxonomy for reporting.

```
ACTION TYPE TAXONOMY:

COMMUNICATION:
  - email_sent — Outbound email (reply, follow-up, cold outreach)
  - email_drafted — Draft created, pending owner review
  - message_sent — Telegram/Slack/SMS message sent
  - call_scheduled — Meeting/call booked on calendar
  - call_completed — Phone/video call finished
  - notification_sent — Alert sent to owner or team member

CUSTOMER:
  - ticket_created — Support ticket opened
  - ticket_resolved — Support ticket closed
  - ticket_escalated — Ticket routed to engineering/owner
  - customer_contacted — Proactive outreach to customer
  - feedback_logged — Customer feedback recorded

SALES:
  - lead_created — New prospect added to CRM
  - lead_updated — Prospect info or stage changed
  - lead_contacted — Outreach to lead
  - deal_advanced — Deal moved to next stage
  - deal_lost — Deal marked as lost with reason
  - deal_won — Deal closed successfully

CONTENT:
  - social_post_published — Twitter, LinkedIn, Instagram post
  - content_created — Blog post, article, thread drafted
  - content_scheduled — Post queued for future publication

OPERATIONS:
  - decision_prepared — Decision memo created
  - briefing_delivered — Morning/evening brief sent
  - report_generated — Metrics or analytics report created
  - task_created — New task assigned
  - task_completed — Task marked done
  - follow_up_scheduled — Future action queued

SYSTEM:
  - scan_completed — Periodic scan finished (inbox, pipeline, metrics)
  - anomaly_detected — KPI anomaly identified
  - error_occurred — Action failed, error logged
  - config_changed — Settings or threshold modified
```

### Step 4: Track Outcomes Over Time

Many actions have delayed outcomes. Update the log when outcomes arrive.

```
OUTCOME TRACKING:

1. When action has a follow-up date, set a check:
   state_db(action="set_outcome_check", action_id=act_id, check_date=follow_up_date)

2. When the check triggers, evaluate outcome:
   - Did the contact reply? → outcome = "replied" or "no_reply"
   - Did the deal advance? → outcome = "deal_advanced" or "no_change"
   - Was the ticket resolved? → outcome = "resolved" with resolution time
   - Did the metric recover? → outcome = "recovered" or "still_anomalous"

3. Update the original action record:
   state_db(action="update_action", id=act_id, data={
     "outcome.measurable_result": result,
     "outcome.status": final_status,
     "outcome.resolved_at": timestamp
   })

4. Feed outcome data back into future decisions:
   - Track response rates by nudge number (nudge #1: 45%, #2: 28%, #3: 12%)
   - Track resolution times by issue category
   - Track which email templates get best responses
   - Track which channels are most effective per contact

EFFECTIVENESS METRICS (updated weekly):
  state_db(action="calculate_effectiveness", period="7d")
  → Follow-up response rate: X%
  → Average deal cycle after nudge: Y days
  → Support auto-resolve rate: Z%
  → Briefing items actioned by owner: W%
```

### Step 5: Generate Reports

Produce regular summaries of all actions taken.

```
DAILY SUMMARY (end of day or on request):
  state_db(action="get_actions", date=today)
  Group by skill, count by action_type, list outcomes.

WEEKLY DIGEST (Friday 5pm, automatic):
  state_db(action="get_actions", date_range="this_week")
  Sections:
    1. Action count by category
    2. Top outcomes (deals closed, tickets resolved)
    3. Failed actions and reasons
    4. Follow-ups scheduled for next week
    5. Effectiveness metrics vs previous week
    6. Notable patterns or anomalies in agent behavior

MONTHLY REPORT (1st of month):
  state_db(action="get_actions", date_range="last_month")
  Sections:
    1. Total actions by category (month-over-month comparison)
    2. Revenue impact: deals influenced, churn prevented
    3. Time saved: estimated hours of work automated
    4. Effectiveness trends
    5. Recommendations for improving agent performance
```

### Step 6: Enable Natural Language Querying

The owner should be able to ask questions about past actions.

```
QUERY PATTERNS:

"What did you do about Acme?"
  → state_db(action="search_actions", filter={contact_company: "Acme"})
  → Return all actions involving Acme, sorted by date

"Show me all follow-ups sent this week"
  → state_db(action="search_actions", filter={
       action_type: "email_sent", skill: "follow-up-engine", date_range: "this_week"
     })

"What happened with the TechStart deal?"
  → state_db(action="search_actions", filter={crm_deal_id: "deal_789"})
  → Return complete action timeline for that deal

"How many tickets did we handle?"
  → state_db(action="count_actions", filter={
       action_type: ["ticket_created", "ticket_resolved", "ticket_escalated"],
       date_range: requested_period
     })

"What's still pending?"
  → state_db(action="search_actions", filter={
       outcome.status: "pending", follow_up.needed: true
     })
  → Return all open action items with follow-up dates
```

---

## Output Format

### Individual Action Log Entry (real-time, appended silently)

```
[2026-03-30 14:23:00] [follow-up-engine] Sent follow-up #2 to James Wu (TechStart)
  Channel: email | Deal: $24K | Next check: April 2
```

### Daily Activity Summary

```
ACTION LOG — {date}
=======================

Total actions: {N}
By category: communication {X} | customer {X} | sales {X} | operations {X} | system {X}

TIMELINE:
  09:30  Sent outreach email to Sarah Chen (Acme Corp) — success
  10:15  Published Twitter thread (3 tweets, AI tips) — success
  11:00  Call with John (Demo Corp) — completed, 12 min
  14:00  Moved Acme Corp deal to Negotiation — success
  15:30  Sent follow-up to 3 stale prospects — 2 success, 1 bounced
  16:00  Generated weekly KPI report — sent to owner

OUTCOMES:
  Success: {X} | Partial: {X} | Failed: {X} | Pending: {X}

PENDING FOLLOW-UPS:
  - Sarah Chen — follow up by Jan 18
  - Demo Corp — send proposal by Jan 16
```

### Weekly Digest

```
WEEKLY ACTION DIGEST — Week of {date}
==========================================

SUMMARY:
  Total actions: 187 (up from 162 last week)
  Actions by owner: 23 (decisions, approvals, personal responses)
  Actions by agent: 164 (automated triage, follow-ups, support)
  Estimated time saved: ~18 hours

BY CATEGORY:
  Communication:  89 (47%) — 62 emails, 18 messages, 9 calls scheduled
  Customer:       41 (22%) — 28 tickets resolved, 8 escalated, 5 feedback logged
  Sales:          31 (17%) — 12 leads contacted, 8 deals updated, 3 won
  Operations:     19 (10%) — 7 reports, 5 briefs, 4 decisions, 3 tasks
  System:          7 (4%)  — 5 scans, 2 anomalies detected

EFFECTIVENESS:
  Follow-up response rate: 62% (up from 58%)
  Support auto-resolve rate: 41% (up from 38%)
  Email draft approval rate: 89% (owner approved 89% without edits)
  Average response time: 1.8 hours (within SLA)

REVENUE IMPACT:
  Deals influenced by agent actions: 4 ($86K total pipeline)
  Deals closed with agent-drafted follow-ups: 1 ($12K)
  Churn prevented (re-engaged quiet customers): 2 ($4.8K MRR saved)

TOP WINS:
  1. Sent 12 follow-up nudges — 7 replies received
  2. Resolved 28 support tickets — 3.2 hour avg resolution
  3. Prepared 3 decision memos — all actioned by owner

ISSUES:
  - 3 emails bounced (bad addresses, CRM updated)
  - 1 metric check failed (dashboard timeout, retried successfully)
  - 2 follow-ups unanswered after 3 nudges (contacts marked cold)

PATTERNS:
  - Tuesday emails get 2x replies vs Monday
  - LinkedIn posts with questions get 3x engagement
  - P1 tickets resolve 40% faster when escalated immediately vs after triage

NEXT WEEK FOLLOW-UPS:
  Monday: 4 items due
  Tuesday: 2 items due
  Wednesday: 3 items due
  Thursday: 1 item due
  Friday: Weekly digest generation
```

---

## Integration Points

### Automatic Logging Hooks

These actions auto-trigger a log entry:
- `email_send` tool completes → log communication action
- `send_message` tool completes → log communication action
- `prospect_tool` updates a deal → log sales action
- `calendar_create` or `calendar_update` → log operations action
- `sms_send` completes → log communication action
- `browser_navigate` completes a workflow → log system action
- Any skill's main workflow completes → log operations action

### Feeding Other Skills

- **chief-of-staff** reads logs for daily briefings and weekly reviews
- **follow-up-engine** reads logs to track what was sent and when
- **kpi-watcher** reads logs for activity-based metrics (emails/day, posts/week)
- **customer-support-ops** reads logs for ticket lifecycle tracking
- **calendar-intelligence** reads logs for post-meeting follow-up tracking

---

## Privacy & Sensitivity

- Never log passwords, API keys, or auth tokens in details/evidence
- Truncate email bodies to first 100 chars in log (full content stays in email system)
- Mark sensitive actions (HR, legal, financial) with `"sensitivity": "high"`
- High-sensitivity logs excluded from automated reports — owner must query explicitly
- Owner can request log deletion: "delete logs from [date]" → remove entries

---

## Retention

- Keep detailed logs for 90 days
- After 90 days, compress to weekly summaries
- Weekly summaries kept indefinitely
- Owner can override: "keep all logs" or "delete logs older than 30 days"
- Export before deletion: always offer JSONL export before any purge

---

## Examples

### Example 1: Automatic Post-Action Log

**Input:** (Automatic) Follow-up engine just sent a nudge email

**Process:**
1. Receive action completion signal from follow-up-engine skill
2. Construct action record with all metadata
3. Write to state_db, CRM, file log, and audit trail
4. Schedule outcome check for follow-up date
5. No notification needed (routine action)

**Output:** Action logged silently. Will appear in daily/weekly summaries.

### Example 2: "What did you do about Acme?"

**Input:** "What did you do about Acme this week?"

**Process:**
1. Query state_db for all actions involving Acme Corp this week
2. Sort by timestamp, group by skill
3. Include outcomes and pending items

**Output:**
```
ACME CORP — Actions This Week (9 actions, 4 skills):

March 28 (Mon):
  - [support] Received P1 ticket: API 500 errors. Escalated to engineering.
  - [support] Sent acknowledgment email to Sarah Chen.
  - [follow-up] Notified owner: enterprise customer issue.

March 29 (Tue):
  - [support] Engineering deployed fix. Confirmed with Sarah.
  - [support] Ticket resolved. Resolution time: 18 hours.
  - [chief-of-staff] Flagged renewal deadline in morning brief.

March 30 (Wed):
  - [decision-memo] Created renewal decision memo (3 options).
  - [calendar] Prepped meeting brief for 2pm Sarah/James call.
  - [inbox-triage] Drafted owner's reply to Sarah's pricing question.

PENDING:
  - Renewal contract: owner chose Option B, contract sent, awaiting signature.
  - Next check: April 2 (signature deadline).
```

### Example 3: Export for Investor Update

**Input:** "Export all actions for March for the investor update"

**Process:**
1. Query state_db for all March actions
2. Generate summary statistics
3. Export raw JSONL for detailed analysis
4. Create formatted markdown report

**Output:**
```
March 2026 — Agent Activity Export

Files generated:
  - ~/.hermes/logs/exports/2026-03-actions.jsonl (raw data, 612 records)
  - ~/.hermes/reports/2026-03-monthly-summary.md (formatted report)

Highlights for investor deck:
  - 612 automated actions taken
  - ~72 hours of manual work automated
  - 4 deals directly influenced ($142K pipeline)
  - 89% email draft approval rate (high-quality output)
  - 41% support tickets auto-resolved
  - 67% follow-up response rate
```

### Example 4: Failed Action Logging

**Input:** (Automatic) Email send failed due to invalid address

**Process:**
1. Log action with outcome.status = "failed" and error details
2. Update CRM: mark email as invalid
3. Notify follow-up-engine: skip this contact's email channel
4. Add to daily summary under "Issues"

**Output:**
```
[2026-03-30 15:45:00] [follow-up-engine] FAILED: Email to john@oldcompany.com bounced
  Error: 550 Mailbox not found | CRM updated: email marked invalid
  Next: Try LinkedIn or phone if available
```
