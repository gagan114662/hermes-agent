# CRM & Sales Copilot

## Purpose

Manage the full prospect pipeline from lead discovery to closed deal. Research leads, score them using the BANT framework, draft personalized outreach, track deal progression through pipeline stages, and log every interaction. Act as a tireless sales operations assistant that never lets a deal fall through the cracks.

## When to Use

Activate this skill when:
- User says "research this lead", "look up [company/person]", "who is [prospect]"
- User says "add to pipeline", "new lead", "log this prospect"
- User says "score this lead", "is this worth pursuing", "qualify [prospect]"
- User says "draft outreach to [prospect]", "write a cold email", "follow up with [lead]"
- User says "show me my pipeline", "what deals are active", "what needs follow-up"
- User says "update [prospect] to [stage]", "move [deal] forward", "mark [deal] as closed"
- User forwards an inbound inquiry or meeting request from a potential customer
- A new lead comes in via website, email, or referral (auto-trigger)
- A deal has been stale for more than 7 days without activity (auto-trigger)

## What You Need

### Tools
- `web_search` — Research prospects, companies, industries, competitors, trigger events
- `web_extract` — Pull detailed info from LinkedIn, company websites, Crunchbase, news articles
- `read_file` — Load CRM data, pipeline files, outreach templates, prior interaction logs
- `write_file` — Update CRM records, save research, log interactions
- `search_files` — Find prior mentions of a prospect, related companies, similar deals
- `send_message` — Send outreach emails, follow-ups, notifications to owner
- `browser_navigate` — Access LinkedIn Sales Navigator, company sites, review sites
- `prospect_tool` — Direct CRM operations: add, update, search, list prospects
- `state_db` — Track deal stages, follow-up schedules, pipeline metrics

### Data Needed
- Prospect name, company, email, phone (whatever is available)
- Source of the lead (inbound, referral, outbound, event)
- Owner's ideal customer profile (ICP) and deal-breaker criteria
- Pricing tiers and typical deal sizes
- Owner's value proposition and differentiators
- Outreach tone and style preferences

---

## Pipeline Stages

Every deal moves through these stages. Each stage has entry criteria and required actions:

```
STAGE 1: LEAD
  Entry: Any new potential customer identified
  Status: Unqualified, needs research
  Actions: Research company/person, initial BANT assessment
  Exit criteria: Enough info to determine if worth pursuing
  Auto-move: → Qualified (if BANT score >= 6) or → Disqualified

STAGE 2: QUALIFIED
  Entry: Lead passes initial BANT screen (score >= 6/12)
  Status: Worth pursuing, needs outreach
  Actions: Personalized first outreach, establish contact
  Exit criteria: Prospect responds or 3 outreach attempts made
  Auto-move: → Proposal (if positive response) or → Nurture (if no response)

STAGE 3: PROPOSAL
  Entry: Prospect engaged, expressed interest, needs a formal offer
  Status: Active conversation, preparing or sent proposal
  Actions: Draft proposal, send pricing, schedule demo/call
  Exit criteria: Proposal delivered and discussed
  Auto-move: → Negotiation (if they want to proceed) or → Lost (if declined)

STAGE 4: NEGOTIATION
  Entry: Prospect reviewing proposal, discussing terms
  Status: Back-and-forth on pricing, scope, timeline, terms
  Actions: Handle objections, adjust terms, involve owner for key decisions
  Exit criteria: Verbal agreement or clear rejection
  Auto-move: → Closed Won or → Closed Lost

STAGE 5: CLOSED WON
  Entry: Deal signed, payment received or committed
  Status: Customer acquired
  Actions: Log final deal value, trigger onboarding, send welcome, celebrate

STAGE 5 (alt): CLOSED LOST
  Entry: Prospect declined at any stage
  Status: Deal dead (for now)
  Actions: Log reason for loss, schedule re-engagement in 90 days, capture learnings

NURTURE (parallel track):
  Entry: Prospect went cold but is still a fit
  Status: Periodic touchpoints, waiting for timing to improve
  Actions: Monthly value-add emails, share relevant content, monitor for trigger events
  Re-entry: → Qualified (if they re-engage)
```

---

## Process

### Step 1: Lead Research

When a new lead enters the pipeline:

```
1. Basic company research:
   web_search(query="{company_name} overview funding employees")
   web_extract(url=company_website)
   → Company size, industry, funding stage, revenue (if available), product/service

2. Key person research:
   web_search(query="{prospect_name} {company_name} LinkedIn")
   web_extract(url=linkedin_profile_url)
   → Title, tenure, decision-making authority, career background

3. Trigger event scan (reasons they might buy NOW):
   web_search(query="{company_name} hiring OR funding OR launch OR expansion 2026")
   → Recent funding round, new product launch, job postings suggesting growth,
     leadership change, competitive pressure, compliance deadline

4. Competitive landscape:
   web_search(query="{company_name} competitors OR alternatives")
   → Who are they using now? Are they evaluating options?

5. Fit assessment:
   Compare findings against the owner's ICP:
   → Industry match? Company size match? Budget likely? Problem we solve?
```

### Step 2: BANT Scoring

Score every lead on the BANT framework (each dimension 1-3, total out of 12):

```
BUDGET (1-3):
  3 = Clear budget allocated, or company revenue/funding suggests easy affordability
  2 = Budget likely exists but unconfirmed, mid-size company
  1 = Budget unclear, early-stage or small company, no funding signals

AUTHORITY (1-3):
  3 = Contact is the decision maker (CEO, VP, Head of relevant department)
  2 = Contact is an influencer who can champion internally (senior IC, manager)
  1 = Contact is junior, no clear path to decision maker

NEED (1-3):
  3 = Explicit need expressed (inbound inquiry, RFP, stated problem)
  2 = Implied need (job postings suggest the problem, industry trend)
  1 = No clear need identified, speculative fit

TIMELINE (1-3):
  3 = Buying now or within 30 days (active evaluation, deadline-driven)
  2 = Buying within 1-3 months (exploring options, no urgency)
  1 = No timeline, "just looking", 6+ months out

SCORING THRESHOLDS:
  10-12 = HOT — Prioritize immediately, personal outreach from owner
  7-9   = WARM — Strong candidate, begin outreach sequence
  4-6   = COOL — Worth a touchpoint, but don't invest heavily yet
  1-3   = COLD — Disqualify or add to long-term nurture list
```

Log the score:
```
write_file("crm/leads/{company_slug}/score.md", bant_assessment)
prospect_tool(action="update", id=prospect_id, bant_score=total, stage="qualified")
```

### Step 3: Personalized Outreach

Draft outreach based on BANT score and research:

```
1. Select outreach channel:
   — Email preferred for first cold outreach
   — LinkedIn DM if email unknown or email bounced
   — Telegram/WhatsApp if warm intro or existing relationship

2. Personalize the message using research:
   — Reference something specific about THEM (not generic flattery)
   — Connect their situation to the value you provide
   — Keep it short: 3-5 sentences for cold, 5-8 for warm
   — One clear CTA: reply, book a call, check a link

3. Outreach templates by temperature:

HOT LEAD (score 10-12):
   Subject: {Specific trigger event} + how we help
   "Hi {Name}, I noticed {company} just {trigger event}. When companies
   in {industry} hit this stage, they typically face {problem we solve}.
   We helped {similar company} achieve {specific result}.
   Worth a 15-minute call this week?"

WARM LEAD (score 7-9):
   Subject: Quick question about {their challenge}
   "Hi {Name}, I've been following {company}'s work in {space}.
   Curious — are you currently handling {problem} in-house or
   looking at solutions? We've built something that {value prop in 1 line}.
   Happy to share how it might fit your setup."

COOL LEAD (score 4-6):
   Subject: {Relevant content} for {their role/industry}
   "Hi {Name}, thought you might find this useful — {link to relevant
   content/case study}. We see a lot of {role}s at {stage} companies
   running into {challenge}. If that resonates, happy to chat."

REFERRAL/INTRO:
   Subject: {Mutual connection} suggested we connect
   "Hi {Name}, {referrer} mentioned you're working on {topic} at {company}.
   We recently helped {similar situation} and {referrer} thought there
   might be a good fit. Would love to learn more about what you're
   building. Free for a quick call?"

4. Send and log:
   send_message(to=prospect_email, subject=subject, body=body)
   write_file("crm/leads/{company_slug}/interactions.md", outreach_log)
   prospect_tool(action="update", id=prospect_id, last_contact=today, stage="qualified")
```

### Step 4: Follow-Up Cadence

Never let a lead go cold without proper follow-up:

```
FOLLOW-UP SEQUENCE:
  Day 0:  Initial outreach (see Step 3)
  Day 3:  Follow-up #1 — Short, add new value (different angle or content)
  Day 7:  Follow-up #2 — Reference the original + new trigger/insight
  Day 14: Follow-up #3 — Break-up email ("Closing the loop — should I circle back later?")
  Day 30: Nurture add — Move to nurture track, monthly touchpoint

FOLLOW-UP RULES:
  - Never send the same message twice
  - Each follow-up must add new value or a new angle
  - If they reply with "not now", respect it — add to nurture with 90-day re-engage
  - If they reply with "not interested", mark Closed Lost and log reason
  - If they reply positively, move to Proposal stage immediately
  - After 3 no-replies, stop outreach — move to nurture, don't spam

Log every follow-up:
  write_file("crm/leads/{company_slug}/interactions.md", follow_up_entry)
```

### Step 5: Deal Stage Management

As deals progress, update and track:

```
1. For PROPOSAL stage:
   - Draft proposal document based on discovery call notes
   - Include: problem statement, proposed solution, pricing, timeline, terms
   - Send for owner review before delivering to prospect
   - Log proposal sent date and version

2. For NEGOTIATION stage:
   - Track each revision and counter-offer
   - Log objections raised and responses given
   - Flag when owner needs to be involved (pricing exceptions, custom terms)
   - Set deadline for decision to prevent deals from lingering

3. For CLOSED WON:
   - Log final deal value, contract terms, close date
   - Calculate actual sales cycle length
   - Trigger onboarding workflow
   - Send welcome message to new customer
   - Update pipeline metrics

4. For CLOSED LOST:
   - Log specific reason (price, timing, competitor, no budget, ghosted)
   - Schedule 90-day re-engagement check
   - Capture learnings: what could we have done differently?
   - Update win/loss patterns for future scoring improvements
```

### Step 6: Pipeline Reporting

Generate pipeline reports on demand or weekly:

```
1. Pull all active deals:
   prospect_tool(action="list", stage="all_active")
   read_file("crm/pipeline-summary.md")

2. Calculate pipeline metrics:
   - Total pipeline value (sum of all active deal values)
   - Deals by stage (count and value per stage)
   - Average deal age by stage
   - Stale deals (no activity in 7+ days)
   - Expected close dates vs actual pace
   - Win rate (closed won / total closed)
   - Average sales cycle length

3. Compile and deliver report (see Output Format below)
```

---

## Output Format

### Lead Research Report

```
LEAD RESEARCH — {Company Name}
Date: {today}
Source: {inbound/outbound/referral/event}
================================================

COMPANY:
  Name: {company_name}
  Website: {url}
  Industry: {industry}
  Size: {employee_count}
  Funding: {stage} — {total_raised}
  Revenue: {estimated_or_known}
  HQ: {location}
  Founded: {year}

KEY CONTACT:
  Name: {prospect_name}
  Title: {title}
  Email: {email}
  LinkedIn: {url}
  Background: {2-3 sentence career summary}

TRIGGER EVENTS:
  - {Recent funding, hiring, product launch, etc.}
  - {Industry trend or compliance deadline}

BANT SCORE: {total}/12
  Budget: {score}/3 — {reasoning}
  Authority: {score}/3 — {reasoning}
  Need: {score}/3 — {reasoning}
  Timeline: {score}/3 — {reasoning}

RECOMMENDATION: {HOT/WARM/COOL/COLD} — {one sentence justification}
NEXT ACTION: {specific recommended action}
```

### Pipeline Summary

```
PIPELINE REPORT — {date}
========================================

SUMMARY:
  Total active deals: {count}
  Total pipeline value: ${total}
  Expected close this month: ${amount} ({count} deals)
  Win rate (last 30 days): {rate}%
  Avg sales cycle: {days} days

BY STAGE:
  Lead:        {count} deals — ${value}
  Qualified:   {count} deals — ${value}
  Proposal:    {count} deals — ${value}
  Negotiation: {count} deals — ${value}

NEEDS ATTENTION:
  Stale deals (no activity 7+ days):
    - {Company} — {stage} — last activity {date} — ${value}
    - {Company} — {stage} — last activity {date} — ${value}

  Follow-ups due today:
    - {Company} — {action needed}
    - {Company} — {action needed}

TOP DEALS (by value):
  1. {Company} — ${value} — {stage} — {next step}
  2. {Company} — ${value} — {stage} — {next step}
  3. {Company} — ${value} — {stage} — {next step}

RECENTLY CLOSED:
  Won: {Company} — ${value} — {close_date}
  Lost: {Company} — reason: {reason} — {close_date}
```

### Interaction Log Entry

```
INTERACTION — {date} {time}
Prospect: {name} ({company})
Channel: {email/call/meeting/linkedin}
Direction: {inbound/outbound}
Stage: {current_stage}
---
Summary: {2-3 sentence summary of the interaction}
Key takeaway: {most important thing learned}
Next action: {what to do next and when}
BANT update: {any score changes with reasoning}
---
```

---

## Examples

### Example 1: Research a New Lead

**Input:** "Research Vercel for me. They might be a good fit."

**Process:**
1. Web search: Vercel — Next.js company, ~500 employees, Series D ($150M), CEO Guillermo Rauch
2. Trigger events: Just launched v0 AI tool, hiring aggressively in enterprise sales
3. BANT: Budget 3/3 (well-funded), Authority TBD (no contact yet), Need 2/3 (likely based on growth), Timeline 2/3 (active hiring suggests building)
4. Score: 7/12 minimum (warm, higher if we identify the right contact)

**Output:** Full research report with recommendation: "WARM lead. They're scaling fast and likely need {our solution}. Recommend identifying the Head of {relevant department} for outreach."

### Example 2: Draft Cold Outreach

**Input:** "Write a cold email to Sarah at Notion. She's their Head of Ops."

**Process:**
1. Research Sarah + Notion (recent news, her LinkedIn activity)
2. Find trigger: Notion just launched enterprise features, likely scaling ops
3. Draft personalized email referencing their enterprise launch
4. BANT score and log the interaction

**Output:** Personalized outreach email ready to send + CRM entry created.

### Example 3: Pipeline Review

**Input:** "How's our pipeline looking?"

**Process:**
1. Pull all active deals from CRM
2. Calculate metrics: 12 active deals, $340K total pipeline, 3 stale
3. Flag: 2 deals need follow-up today, 1 proposal overdue for response
4. Generate weekly comparison: pipeline up 15% from last week

**Output:** Full pipeline report with stale deal alerts and recommended actions.

### Example 4: Deal Stage Update

**Input:** "Acme said yes. They're signing the contract this week."

**Process:**
1. Update Acme from Negotiation to Closed Won
2. Log final deal value and close date
3. Calculate sales cycle: 23 days from first contact
4. Trigger onboarding workflow
5. Send welcome message
6. Update pipeline metrics

**Output:** "Acme Corp marked as Closed Won — $48K deal, 23-day cycle. Onboarding triggered. Welcome email queued. Pipeline win rate updated to 34%."

---

## Error Handling

- **Prospect email bounces**: Try alternate formats ({first}@{company}.com, {first}.{last}@), check LinkedIn for updated info, ask owner for correct address.
- **Company not found online**: May be pre-launch, very small, or operating under a different name. Ask owner for website URL or more context.
- **BANT score is low but owner wants to pursue**: Respect the owner's judgment — add to pipeline but flag it as "Owner override" in notes. Track separately to measure if owner intuition beats the scoring model.
- **Prospect is at a competitor's customer**: Flag the sensitivity. Research the competitor relationship before outreach to avoid missteps.
- **Duplicate leads**: Before creating a new entry, always search CRM for existing records matching name, email, or company. Merge if found.
- **Stale deal with no response**: After 3 follow-ups with no reply, do not keep emailing. Move to nurture. Notify the owner with recommendation.
