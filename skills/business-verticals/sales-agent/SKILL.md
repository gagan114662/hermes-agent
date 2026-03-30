---
name: sales-agent
description: Post-call sales automation. Owner sends call summary on Telegram → Hermes updates Notion CRM with call notes/deal stage/next follow-up, generates a polished proposal in Google Docs, drafts a follow-up email in Gmail with the proposal linked, and returns all links. Also handles full sales pipeline management, follow-up sequences, and deal tracking. Triggers on: sales call, post-call, proposal, CRM update, deal stage, follow-up, Notion CRM, pipeline, close.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [Sales, CRM, Proposal, Pipeline, Follow-up, Notion, Gmail]
---

# Sales Agent — Post-Call Automation Skill

Hermes acts as the owner's full-time sales operations assistant. After every sales call, the owner sends a quick Telegram message — free-form, no templates required — and Hermes handles everything else: CRM, proposal, follow-up email, and calendar reminder. All within 60 seconds.

---

## 1. Post-Call Workflow (Core Feature)

### Trigger

This skill activates when a Telegram message contains any of the following signals:
- Signal words: "just called", "spoke with", "call with", "meeting with", "just met", "had a call"
- Prospect or company name alongside deal context
- Deal stage indicators: "interested", "wants a demo", "sent proposal", "closed", "lost", "not interested"
- Follow-up intent: a date, "follow up", "check back", "circle back"

The message can be completely free-form. Hermes parses it intelligently — the owner does not need to follow any structure.

---

### Step 1: Parse the Message

Hermes uses an LLM pass to extract structured data from the raw Telegram message.

**Fields extracted:**

| Field | Description |
|---|---|
| `prospect_name` | First name of the contact |
| `company_name` | Company or business name |
| `contact_role` | Title or role if mentioned |
| `deal_stage` | One of: discovery, demo, proposal, negotiation, closed-won, closed-lost |
| `pain_points` | List of problems or frustrations mentioned |
| `budget` | Budget range or signal (e.g., "$500-800/month", "tight", "no budget issues") |
| `timeline` | When they want to start or make a decision |
| `next_steps` | What was agreed on the call |
| `follow_up_date` | Specific date, or "3 business days" if not mentioned |
| `lost_reason` | If closed-lost: why (price, competitor, timing, no decision) |
| `vertical` | Industry detected (dental, med spa, restaurant, e-commerce, law, generic) |

**Parsing examples:**

Input:
```
Just spoke with Sarah at Acme Corp. She runs a dental practice, 3 locations. Pain: missing calls, losing patients. Budget: $500-800/month. She wants a demo. Following up Thursday.
```

Extracted:
```json
{
  "prospect_name": "Sarah",
  "company_name": "Acme Corp",
  "deal_stage": "demo",
  "pain_points": ["missing calls", "losing patients"],
  "budget": "$500-800/month",
  "next_steps": "Schedule demo",
  "follow_up_date": "Thursday",
  "vertical": "dental"
}
```

---

Input:
```
Call with Jake - interested, needs to think, follow up in 2 weeks
```

Extracted:
```json
{
  "prospect_name": "Jake",
  "deal_stage": "discovery",
  "next_steps": "Follow up after reflection period",
  "follow_up_date": "2 weeks from today",
  "vertical": "generic"
}
```

---

Input:
```
Lost TechStart — went with competitor, too expensive
```

Extracted:
```json
{
  "company_name": "TechStart",
  "deal_stage": "closed-lost",
  "lost_reason": "price — went with competitor"
}
```

---

### Step 2: Run All Actions in Parallel

Once parsing is complete, Hermes executes the following four actions simultaneously.

---

### Action 1: Update Notion CRM

Create a new deal record if the company does not exist. Update the existing record if it does.

**Database:** Sales Pipeline

**Fields to write:**

```
Company:         [company_name]
Contact:         [prospect_name] — [contact_role if given]
Stage:           [deal_stage]
Pain Points:     [bullet list from pain_points]
Budget:          [budget]
Timeline:        [timeline]
Next Action:     [next_steps]
Follow-up Date:  [follow_up_date]
Call Notes:      [full original message, verbatim]
Last Updated:    [today's date]
Lost Reason:     [lost_reason, if applicable]
Vertical:        [vertical]
```

**Tools:** `notion_create_page`, `notion_update_page`, `notion_query_database`

**Logic:**
1. Query the Sales Pipeline database for a record matching `company_name` or `prospect_name`.
2. If found: update the existing record with new stage, notes, and follow-up date.
3. If not found: create a new record with all fields populated.
4. Return the Notion page URL.

---

### Action 2: Generate Proposal in Google Docs

Create a new Google Doc using the template below. Auto-fill based on extracted call data and vertical.

**Document title:** `[Company Name] — Proposal — [Date]`

**Document structure:**

```
[Company Name] — Proposal
Prepared by: [owner name]  |  [date]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE PROBLEM WE SOLVE FOR YOU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[2-3 sentences written specifically around the pain points mentioned on this call.
Reference the company name and their situation. Do not use generic filler.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT HERMES WILL DO FOR YOU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Based on your business ([vertical]), Hermes will handle:
  • [Vertical-specific task 1]
  • [Vertical-specific task 2]
  • [Vertical-specific task 3]
  • [Vertical-specific task 4]
  • [Vertical-specific task 5]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INVESTMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Tier 1 name]: $[price]/month
  • [Features]

[Tier 2 name]: $[price]/month  ← RECOMMENDED
  • Everything in Tier 1
  • [Additional features]

[Tier 3 name]: $[price]/month
  • Everything in Tier 2
  • [Premium features]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT HAPPENS NEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. You approve this proposal
2. We set up your account and connect your tools (15 minutes)
3. Hermes starts working immediately — you get your first report within 24 hours

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ACCEPT THIS PROPOSAL]  ←  linked CTA
[Book Onboarding Call]  ←  calendar link
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Sharing:**
- Owner: edit access
- Anyone with link: view access

**Tools:** `docs_create`, `docs_insert`, `drive_share`

Return the Google Docs URL.

---

### Action 3: Draft Follow-Up Email in Gmail

Create a draft — do NOT send. The owner reviews and sends manually.

**Subject:** `Following up — [Company Name] + Hermes`

**Body:**

```
Hi [prospect_name],

Really enjoyed our conversation today about [specific pain point from call — be precise, not generic].

As promised, I've put together a proposal tailored to [Company Name]: [Google Doc link]

The short version:
  • [Benefit 1 tied to their specific pain point]
  • [Benefit 2]
  • [Benefit 3]

Most [vertical] businesses see [relevant result] within the first [timeframe].

I've held [follow_up_date] open for our next conversation. Does [suggested time] still work?

[Calendar link]

[Owner name]
```

**Rules:**
- Never send — always create as draft
- Pain points must reference what was actually said on the call, not a generic line
- Benefits must be specific to their vertical and situation
- If no follow-up date was given, default to 3 business days from today

**Tools:** `gmail_create_draft`

Return the Gmail draft URL.

---

### Action 4: Schedule Follow-Up Reminder

Create a calendar event for the follow-up date.

**Event:**
```
Title:    Follow up: [Company Name] — [prospect_name]
Date:     [follow_up_date]
Time:     10:00am (default unless specified)
Notes:    Deal stage: [deal_stage] | Next action: [next_steps]
```

If no follow-up date was mentioned in the call notes, default to 3 business days from today.

**Tools:** `gcal_create_event`

---

### Step 3: Deliver Confirmation via Telegram

After all four actions complete, send a single summary message back to the owner on Telegram:

```
✅ Post-call done for [Company Name] / [prospect_name]

📋 CRM: [Notion deal URL]
📄 Proposal: [Google Docs URL]
📧 Gmail draft: [Gmail draft URL]
📅 Follow-up: [follow_up_date] at [time]

Deal stage: [deal_stage]
Next action: [next_steps]
```

**Target delivery time:** Within 60 seconds of the owner sending the call notes.

---

## 2. Sales Pipeline Management

### Daily Pipeline Review — 9:00am

Every morning at 9am, Hermes queries the Notion CRM and runs the following checks:

1. **No activity in >3 days** — deals where `Last Updated` is more than 3 days ago and stage is not closed. Flag for follow-up.
2. **Proposal sent >5 days with no response** — stage is "proposal" and `Last Updated` is more than 5 days ago. Flag for nudge.
3. **Follow-up dates today or overdue** — `Follow-up Date` is today or in the past. Flag as urgent.

Hermes sends a daily briefing to Telegram:

```
📋 Pipeline — [date]

Action needed today:
  • [X] follow-ups due (overdue or today)
  • [X] proposals with no response >5 days
  • [X] deals with no activity >3 days

[List each deal with name, stage, and last contact date]

Total open deals: [X]
Pipeline value: $[X]/month potential
```

---

### Follow-Up Sequences by Deal Stage

Hermes manages automated follow-up drafts. All emails are created as drafts — owner sends manually or approves for auto-send (configured per owner preference).

#### Discovery → Demo

| Day | Action |
|---|---|
| Day 0 | Follow-up email drafted after call |
| Day 3 | "Did you get a chance to look at this?" |
| Day 7 | "Quick question — is this still a priority?" |
| Day 14 | "I'll close this out unless I hear from you — totally understand if timing isn't right" |

#### Proposal Sent

| Day | Action |
|---|---|
| Day 0 | Proposal sent (Google Doc link) |
| Day 2 | "Quick check-in — any questions on the proposal?" |
| Day 5 | "I wanted to make sure you had everything you need to make a decision" |
| Day 10 | Offer a call: "Would it help to walk through it together for 15 minutes?" |

#### Closed Won

| Timing | Action |
|---|---|
| Immediately | Send onboarding instructions + calendar link to book setup call |
| Day 1 | "Did you get our onboarding email? Let me know if anything is unclear." |
| Day 7 | First check-in after going live: "How are things feeling so far?" |

#### Closed Lost

| Timing | Action |
|---|---|
| Immediately | Log `lost_reason` in CRM. No email sent. |
| Day 0 | Send a single graceful close: "Thanks for considering us — if anything changes, I'm always here." |
| Day 90 | Re-engage nurture: "Checking back in — a lot has changed, worth a quick chat?" |

**Rule:** Never contact a closed-lost prospect again within the first 90 days.

---

## 3. Deal Analytics — Weekly Report

Every Monday at 8:00am, Hermes queries the CRM and sends the weekly sales report via Telegram:

```
💼 Sales Weekly — [Mon date] to [Sun date]

Pipeline:
  Discovery:       [X] deals  ($[X] potential MRR)
  Demo scheduled:  [X]
  Proposal sent:   [X]
  Negotiation:     [X]

Closed this week:
  Won:   [X] deals  ($[X] MRR added)
  Lost:  [X] deals  (top reason: [reason])

Conversion rates:
  Discovery → Demo:     [X]%
  Demo → Proposal:      [X]%
  Proposal → Close:     [X]%

Avg deal cycle:          [X] days
Total pipeline value:    $[X] MRR
Projected close (month): $[X] MRR

Action items:
  Follow-ups needed today: [X]
```

---

## 4. Proposal Templates by Vertical

When generating the proposal doc, Hermes selects the appropriate industry frame based on the detected `vertical`.

### Dental

**Problem section focus:** Missed calls mean lost patients. Every unanswered call is a person who called a competitor.

**What Hermes handles:**
- Missed call recovery and automatic callbacks
- Patient recall campaigns (hygiene, treatment follow-ups)
- New patient inquiry handling
- Review requests after appointments
- Insurance pre-auth follow-ups

---

### Med Spa

**Problem section focus:** Booking no-shows and lapsed clients cost more than most marketing budgets.

**What Hermes handles:**
- Online appointment booking and confirmations
- Before/after content collection for social media
- Review management (Google, Yelp)
- Lapsed client re-engagement
- Consultation follow-up sequences

---

### Restaurant

**Problem section focus:** Negative reviews and no-show reservations eat margin. Word of mouth can be engineered.

**What Hermes handles:**
- Reservation management and reminders
- Review response drafting (Google, Yelp, TripAdvisor)
- Supplier ordering coordination
- Catering inquiry follow-up
- Loyalty program outreach

---

### E-commerce

**Problem section focus:** Most revenue lost to abandoned carts and one-time buyers who never return.

**What Hermes handles:**
- Customer service ticket automation
- Abandoned cart follow-up sequences
- Post-purchase review requests
- Return and refund communication
- Repeat purchase win-back campaigns

---

### Law Firm

**Problem section focus:** Billing leakage and slow intake lose cases before they start.

**What Hermes handles:**
- New client intake and document collection
- Billing reminder sequences
- Deadline and filing date tracking
- Client status update communications
- Referral follow-up tracking

---

### Generic SMB

**Problem section focus:** Owners spend more time on admin than on the work that actually makes money.

**What Hermes handles:**
- Inbox triage and response drafting
- Lead follow-up and nurture sequences
- Weekly business reporting
- Appointment scheduling and reminders
- Document and proposal generation

---

## 5. Tools

| Task | Tool |
|---|---|
| Parse call notes | LLM (structured extraction from free-form text) |
| Update CRM | Notion MCP — `notion_create_page`, `notion_update_page`, `notion_query_database` |
| Generate proposal | Google Docs MCP — `docs_create`, `docs_insert`, `drive_share` |
| Draft follow-up email | Gmail MCP — `gmail_create_draft` |
| Schedule follow-up | Google Calendar MCP — `gcal_create_event` |
| Return confirmation | `send_message` (Telegram) |
| Daily pipeline review | Notion MCP — `notion_query_database` |
| Follow-up sequences | `gmail_create_draft`, `send_email`, `sms_send` |
| CRM logging | `crm_save`, `crm_log`, `crm_deal` |
| Weekly report | Notion MCP + `send_message` |

---

## 6. What Hermes Never Does

- **Never sends the proposal email without owner review.** Always a draft. Always.
- **Never marks a deal closed-won until payment is confirmed.** Stage stays "negotiation" until money clears.
- **Never skips the CRM update.** Every call, every conversation, every lost deal — all logged.
- **Never promises a specific ROI number in proposals** without explicit owner approval.
- **Never closes a deal as lost without logging the reason.** Loss data is the most valuable data in sales.
- **Never contacts a closed-lost prospect within 90 days.** One graceful exit message, then silence until the nurture window opens.
- **Never auto-sends any email** unless the owner has explicitly enabled auto-send for that sequence.
