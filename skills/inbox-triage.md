# Inbox Triage & Response Drafting

## When to Use

Activate this skill when:
- User says "check my inbox", "triage my messages", "what needs my attention"
- User says "draft replies", "respond to my emails", "handle my messages"
- Scheduled morning/evening inbox sweep (cron trigger)
- New high-priority message detected (webhook trigger from email/Telegram/Slack)
- User says "who's waiting on me", "any urgent messages"

## What You Need

### Tools
- `email_read` — Fetch unread emails via IMAP (inbox, sent, spam)
- `email_send` — Send or reply to emails via SMTP
- `send_message` — Send Telegram messages (notifications to owner, replies to contacts)
- `web_search` — Look up sender context, company info, recent news
- `prospect_tool` — Check CRM for sender relationship history, deal stage, customer tier
- `state_db` — Read/write triage decisions, follow-up dates, message metadata
- `file_tools` — Log triage results for audit trail

### Data Needed
- Access to all message channels (email credentials, Telegram bot token, Slack token)
- Owner's contact priority list (VIPs, investors, key customers, team members)
- Business context: current deals, active projects, pending decisions
- Owner's communication style/tone preferences

## Process

### Step 1: Collect All Unread Messages

Pull messages from every channel into a unified queue.

```
1. Fetch unread emails:
   email_read(folder="INBOX", status="UNSEEN", limit=50)

2. Fetch Telegram messages since last check:
   telegram_get_updates(offset=last_processed_update_id)

3. Fetch Slack DMs and mentions:
   slack_get_unread(channels=["dm", "mentions"])

4. Merge into a single list, sorted by timestamp (oldest first)
```

For each message, extract:
- `sender` — name, email, phone, platform
- `subject` — email subject or first line of message
- `body` — full content
- `timestamp` — when it arrived
- `channel` — email / telegram / slack / sms
- `thread_id` — for threading replies
- `attachments` — file names, sizes

### Step 2: Enrich Sender Context

For each unique sender, pull context:

```
1. Check CRM:
   prospect_tool(action="search", query=sender_email)
   → Returns: customer tier, deal stage, last interaction, lifetime value

2. Check recent email history:
   email_read(folder="SENT", search=f"to:{sender_email}", limit=5)
   → Returns: what we last said to them, any promises made

3. If sender is unknown, search the web:
   web_search(query=f"{sender_name} {sender_company}")
   → Returns: LinkedIn profile, company info, relevance to our business
```

### Step 3: Classify Each Message

Assign each message to exactly one bucket:

**URGENT (respond within 1 hour)**
- Sender is a VIP (investor, key customer, partner)
- Contains urgency keywords: "ASAP", "urgent", "deadline today", "blocking", "down", "broken"
- Mentions a deadline within 24 hours
- Payment or billing issue from active customer
- Legal or compliance matter

**NEEDS REPLY (respond within 4 hours)**
- Direct question requiring owner's input
- Meeting request or scheduling need
- Customer inquiry about pricing, features, onboarding
- Team member asking for approval or direction
- Warm intro or referral from known contact

**DELEGATE (route to appropriate person/system)**
- Support ticket that doesn't need owner → route to support skill
- Sales inquiry from inbound lead → route to CRM pipeline
- Technical question → route to engineering channel
- Accounting/invoice matter → route to bookkeeper

**FOLLOW-UP LATER (snooze 2-7 days)**
- Newsletter or industry update worth reading later
- Non-urgent proposal or partnership pitch
- Conference or event invitation (check calendar first)
- Request that requires research before responding

**IGNORE (archive, no action needed)**
- Marketing spam, cold outreach with no relevance
- Automated notifications already handled by systems
- CC'd on thread where no action is needed
- Duplicate messages

### Step 4: Draft Responses

For each message in URGENT and NEEDS REPLY, draft a response.

**Drafting rules:**
1. Match the sender's formality level (formal for investors, casual for team)
2. Keep responses concise — aim for 3-5 sentences max
3. Answer the actual question asked, don't dodge
4. If you can't answer definitively, say what you'll do next and when
5. Include a clear next step or call to action
6. Never promise specific dates without checking the calendar first

**Response templates by type:**

Meeting request:
```
Check calendar_check(date_range=proposed_times) first.
If available: "Works for me. Sending invite now." + calendar_create()
If conflict: "I'm booked then. How about [alternative]?" + propose 3 slots
```

Customer question:
```
Check CRM for customer tier and history.
Tier 1 (enterprise): Warm, personal, fast. "Great question, [Name]..."
Tier 2 (growth): Friendly, helpful. "Thanks for reaching out..."
Tier 3 (free/trial): Helpful but efficient. Point to docs if applicable.
```

Investor/VIP:
```
Always warm, always responsive. "Thanks for the note, [Name]."
If it needs owner's personal touch, flag for review instead of auto-sending.
```

### Step 5: Execute Actions

```
For URGENT messages:
  1. Draft response
  2. Send notification to owner via Telegram:
     send_message(chat_id=owner_id, text="URGENT from {sender}: {summary}. Draft reply ready.")
  3. If owner approves (or auto-send is enabled for this sender), send reply
  4. Log action in state_db

For NEEDS REPLY messages:
  1. Draft response
  2. Queue for owner review (batch at end of triage)
  3. If no review within 4 hours, send notification reminder

For DELEGATE messages:
  1. Forward to appropriate person/channel with context
  2. Log delegation in state_db with follow-up date

For FOLLOW-UP LATER messages:
  1. Set snooze in state_db with resurface date
  2. Archive from inbox

For IGNORE messages:
  1. Archive immediately
  2. If sender is in CRM, note the contact attempt
```

### Step 6: Report to Owner

Compile triage summary and send via preferred channel (Telegram or email).

## Output Format

### Triage Summary (sent to owner)

```
INBOX TRIAGE — {date} {time}
================================

URGENT (3 messages)
  1. [EMAIL] Sarah Chen (Acme Corp, Tier 1 customer)
     Re: API integration breaking on v2.3
     → Draft reply ready. Escalated to engineering.

  2. [TELEGRAM] Raj Patel (investor)
     Asking for Q1 metrics deck
     → Draft reply ready. Need your approval to send.

  3. [EMAIL] support@stripe.com
     Payment failed for customer #4821
     → Auto-retrying. Customer notified.

NEEDS REPLY (5 messages)
  4. [EMAIL] Mike Torres — Meeting request for Thursday
     → Conflict detected. Proposed 3 alternatives.

  5. [SLACK] Dev team — Deploy approval needed
     → Forwarded checklist. Awaiting your go/no-go.

  ... (truncated, full list in dashboard)

DELEGATED: 4 messages routed
SNOOZED: 7 messages (resurface dates set)
ARCHIVED: 12 messages (spam/noise)

Total processed: 31 messages in 2m 14s
```

### Per-Message Draft (for review)

```
TO: sarah.chen@acme.com
RE: API integration breaking on v2.3
DRAFT:
  Hi Sarah,

  Thanks for flagging this. I've escalated to our engineering team
  and they're looking into the v2.3 regression now. You should see
  a fix deployed within the next 4 hours.

  In the meantime, rolling back to v2.2 should unblock you.
  Let me know if you need anything else.

  Best,
  [Owner name]

[APPROVE] [EDIT] [SKIP]
```

## Examples

### Example 1: Morning Triage

**Input:** "Check my inbox and handle what you can"

**Process:**
1. Pull 23 unread emails, 8 Telegram messages, 3 Slack DMs
2. Enrich: 15 known contacts (CRM), 8 unknown (web search), 11 spam
3. Classify: 2 urgent, 6 need reply, 3 delegate, 8 follow-up, 15 ignore
4. Draft 8 responses, send 15 to archive, route 3 to team
5. Send summary to owner with draft reviews

**Output:** Triage summary + 8 draft replies queued for approval

### Example 2: Urgent Interrupt

**Input:** (Automatic) New email from investor with "urgent" in subject

**Process:**
1. Detect urgency: sender=VIP + keyword match
2. Skip batch processing, handle immediately
3. Check CRM: last interaction 3 days ago, relationship=warm
4. Draft warm, responsive reply
5. Ping owner on Telegram: "Urgent from [investor]. Draft ready."

**Output:** Owner notified within 30 seconds of email arrival

### Example 3: "Who's waiting on me?"

**Input:** "Who's waiting on me?"

**Process:**
1. Scan sent emails for questions asked to owner with no reply
2. Check CRM for open threads with pending owner action
3. Check calendar for meetings with missing follow-ups
4. Rank by wait time (longest waiting first)

**Output:**
```
People waiting on you (5):
1. Sarah Chen — waiting 3 days for API timeline
2. Mike Torres — waiting 2 days for meeting confirmation
3. Legal team — waiting 1 day for contract review
4. Marketing — waiting 6 hours for campaign approval
5. New lead (James Wu) — waiting 4 hours for demo scheduling
```
