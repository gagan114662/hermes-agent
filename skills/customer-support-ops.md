# Customer Support Operations

## When to Use

Activate this skill when:
- User says "handle support tickets", "check support queue", "answer customer questions"
- User says "what are customers complaining about", "support insights", "common issues"
- New support ticket arrives (email, chat widget, Telegram, or form submission)
- Customer sends a message that looks like a support request (keyword detection)
- Scheduled support queue review (cron: every 2 hours during business hours)
- User says "escalate this", "this is a bug", "route to engineering"
- Weekly product insights report is due

## What You Need

### Tools
- `email_read` — Fetch support emails from support inbox (support@, help@)
- `email_send` — Send support replies, escalation notices, resolution confirmations
- `send_message` — Telegram notifications to owner for escalations, to customers on Telegram
- `web_search` — Research solutions, check known issues, find documentation links
- `prospect_tool` — Look up customer tier, subscription, history, lifetime value
- `state_db` — Track tickets, resolution times, issue categories, satisfaction scores
- `browser_navigate` — Check product status page, internal docs, knowledge base
- `file_tools` — Log support interactions, generate reports

### Data Needed
- Support channel credentials (support inbox, chat widget, Telegram bot)
- Product knowledge base: FAQs, docs, known issues, workarounds
- Customer data: tier, plan, usage, billing status, previous tickets
- Business tone guide: how the company communicates (formal, casual, technical level)
- Escalation paths: who handles what (engineering, billing, product, legal)
- SLA definitions: response time targets by customer tier

## Process

### Step 1: Ingest Support Requests

Pull tickets from all support channels into a unified queue.

```
1. Email support:
   email_read(folder="support@company.com/INBOX", status="UNSEEN")
   → Parse: sender, subject, body, attachments, thread history

2. Telegram support:
   telegram_get_updates(filter="support_bot")
   → Parse: user, message, timestamp, any screenshots/files

3. Form submissions:
   state_db(action="get_new_tickets", source="contact_form")
   → Parse: name, email, category, description, priority self-assessment

4. Chat widget:
   api_call(endpoint="chat/unresolved")
   → Parse: visitor info, conversation transcript, page they were on

5. Social media mentions:
   web_search(query="@company_handle issue OR problem OR help OR broken")
   → Parse: platform, user, complaint text

For each request, create a ticket:
  state_db(action="create_ticket", data={
    id: auto_generated,
    source: channel,
    customer_email: email,
    subject: subject,
    body: body,
    received_at: timestamp,
    status: "new",
    priority: null,  # set in Step 2
    category: null,  # set in Step 2
    assigned_to: null
  })
```

### Step 2: Classify Each Ticket

Assign category, priority, and sentiment to every ticket.

```
CATEGORY CLASSIFICATION:

BILLING
  Keywords: charge, invoice, payment, refund, cancel, subscription, upgrade, downgrade, receipt, pricing
  Examples: "I was charged twice", "How do I cancel?", "Can I get a refund?"

TECHNICAL / BUG
  Keywords: error, broken, not working, crash, 500, timeout, can't login, slow, stuck, bug
  Examples: "The API returns 500", "Dashboard won't load", "Integration is broken"

FEATURE REQUEST
  Keywords: wish, would be nice, can you add, suggestion, feature, missing, need ability to
  Examples: "Can you add SSO?", "Would be great to export to CSV"

ONBOARDING / HOW-TO
  Keywords: how do I, getting started, setup, configure, tutorial, documentation, help with
  Examples: "How do I connect Stripe?", "Where's the API documentation?"

ACCOUNT MANAGEMENT
  Keywords: password, login, account, access, permissions, team, invite, settings
  Examples: "Reset my password", "Add a team member", "Change my email"

SECURITY / COMPLIANCE
  Keywords: security, data, GDPR, privacy, breach, vulnerability, audit, SOC2
  Examples: "Do you have SOC2?", "Where is my data stored?"

PRAISE / FEEDBACK
  Keywords: love, great, awesome, thank you, feedback, suggestion
  Examples: "Love the new feature!", "This has been really helpful"

PRIORITY CLASSIFICATION:

P1 — CRITICAL (respond within 1 hour)
  Conditions:
  - System is down or completely unusable for customer
  - Security incident or data concern
  - Customer is Tier 1 (enterprise, high-value)
  - Contains words: "down", "emergency", "security", "data breach", "all users affected"
  - Payment/billing error causing service disruption

P2 — HIGH (respond within 4 hours)
  Conditions:
  - Feature partially broken but workaround exists
  - Customer is Tier 2 (growth plan)
  - Billing issue (overcharge, failed payment)
  - Blocks customer's work but not production

P3 — MEDIUM (respond within 24 hours)
  Conditions:
  - How-to question
  - Feature request
  - Account management
  - Non-urgent bug report
  - Customer on standard plan

P4 — LOW (respond within 48 hours)
  Conditions:
  - General feedback or praise
  - Feature request from free-tier user
  - Questions answered in documentation
  - Non-customer inquiry

SENTIMENT DETECTION:
  Angry: "unacceptable", "terrible", "worst", "switching to competitor", exclamation marks
  Frustrated: "still not working", "this is the third time", "been waiting"
  Neutral: Factual tone, no emotional language
  Positive: "thanks", "great", "love this"

  If sentiment = Angry AND customer tier >= 2: Auto-escalate to P1
```

### Step 3: Enrich with Customer Context

Before drafting a response, understand who this customer is.

```
For each ticket:
  1. CRM lookup:
     prospect_tool(action="search", query=customer_email)
     → Plan tier, MRR contribution, signup date, lifetime value
     → Previous tickets: count, categories, satisfaction scores
     → Account health: active, at-risk, churning

  2. Recent interactions:
     email_read(search=f"from:{customer_email} OR to:{customer_email}", limit=10)
     → Any ongoing conversations, promises made, open issues

  3. Usage data (if available):
     state_db(action="get_usage", customer=customer_id)
     → Last login, feature usage, API call volume, error rate

  4. Ticket history:
     state_db(action="get_tickets", customer=customer_email)
     → Previous issues, resolution patterns, repeat problems

  Context enrichment affects response:
  - First-time customer with question → warm, welcoming, offer a call
  - Power user with bug report → technical, skip basics, fast-track
  - Angry churning customer → empathetic, escalate to owner, offer concession
  - Enterprise customer → premium treatment regardless of issue type
```

### Step 4: Draft Responses

Generate replies matching the business tone and customer context.

```
RESPONSE PRINCIPLES:
  1. Acknowledge the issue in the first sentence (don't make them repeat it)
  2. Show empathy if frustrated ("I understand this is frustrating")
  3. Provide the solution or clear next step (never just "we're looking into it")
  4. Keep it concise: aim for 3-7 sentences
  5. End with a specific next step or confirmation check
  6. Include relevant doc links if applicable
  7. Match formality to customer (enterprise = more formal, startup = casual)

RESPONSE TEMPLATES BY CATEGORY:

BILLING:
  "Hi {name},

  I checked your account and [explanation of what happened].
  [What we're doing about it: refund issued / charge corrected / here's how to change plan].

  The [refund/credit] should appear within [timeframe]. Let me know if you
  don't see it by then.

  Best, {agent_name}"

TECHNICAL BUG (known issue):
  "Hi {name},

  Thanks for reporting this. We're aware of [issue description] and our
  engineering team is working on a fix. Expected resolution: [timeline].

  In the meantime, here's a workaround: [specific steps].

  I'll follow up once the fix is deployed. Sorry for the inconvenience.

  Best, {agent_name}"

TECHNICAL BUG (new/unknown):
  "Hi {name},

  Thanks for flagging this — I haven't seen this one before. To help our
  engineering team investigate, could you share:
  1. [Specific info needed: browser, steps to reproduce, error message]
  2. [Screenshot if applicable]

  I've escalated this as a priority. We'll get back to you within [timeframe].

  Best, {agent_name}"

HOW-TO:
  "Hi {name},

  Great question! Here's how to [do the thing]:

  1. [Step 1]
  2. [Step 2]
  3. [Step 3]

  Here's the full guide if you want more details: [doc_link]

  Let me know if you run into any issues.

  Best, {agent_name}"

FEATURE REQUEST:
  "Hi {name},

  Thanks for the suggestion! [Acknowledge the value of the idea].
  I've added this to our product roadmap for the team to review.

  [If similar feature exists]: In the meantime, you might find [existing feature]
  helpful for this use case.

  [If on roadmap]: Good news — this is actually on our roadmap for [quarter/timeline].

  Appreciate the feedback!

  Best, {agent_name}"

ANGRY CUSTOMER:
  "Hi {name},

  I'm sorry about this experience — I understand how frustrating [specific issue] is,
  especially when [acknowledge their specific situation].

  Here's what I'm doing right now to fix this:
  1. [Immediate action being taken]
  2. [Timeline for resolution]
  3. [Compensation/goodwill gesture if appropriate]

  I'm personally tracking this to make sure it's resolved. I'll update you by [specific time].

  {Owner name or senior team member name}"
```

### Step 5: Route and Escalate

Not everything should be answered by the AI. Know when to escalate.

```
ESCALATION RULES:

TO ENGINEERING:
  Trigger: New bug, reproducible crash, security vulnerability, data issue
  Action:
    1. Create bug report with reproduction steps, customer info, logs
    2. email_send(to=engineering_lead, subject=f"[BUG-{priority}] {title}")
    3. send_message(chat_id=eng_channel, text=bug_summary)
    4. Respond to customer: "Escalated to engineering, ETA: {timeline}"
    5. Set follow-up check in state_db

TO OWNER:
  Trigger: Enterprise customer angry, churn risk, legal/compliance, strategic account issue
  Action:
    1. send_message(chat_id=owner_id, text=
       "ESCALATION: {customer} ({tier}, ${mrr}/mo) — {issue_summary}.
        Sentiment: {angry/frustrated}. Risk: {churn/legal/reputation}.
        Recommended: [specific action]. Handle personally?")
    2. Draft response for owner to personalize and send

TO BILLING/FINANCE:
  Trigger: Refund >$100, disputed charge, payment infrastructure issue
  Action:
    1. email_send(to=billing_team, subject=f"[BILLING] {customer} — {issue}")
    2. Respond to customer with timeline

AUTO-RESOLVE (no escalation needed):
  - Password resets → send reset link
  - How-to questions → answer with docs
  - Feature requests → log and acknowledge
  - Known issues with workarounds → provide workaround
  - Billing questions (plan details, pricing) → answer from pricing page
```

### Step 6: Track and Analyze

Log every interaction and mine for product insights.

```
TICKET LIFECYCLE TRACKING:
  For each ticket, track:
  - Time to first response (SLA compliance)
  - Number of back-and-forth messages
  - Time to resolution
  - Resolution type: solved, workaround, escalated, self-resolved
  - Customer satisfaction: ask after resolution

  state_db(action="update_ticket", id=ticket_id, data={
    status: "resolved",
    resolution_time: elapsed,
    resolution_type: type,
    messages_count: count,
    satisfaction: score
  })

PATTERN DETECTION (weekly):
  1. Group tickets by category → find most common issues
  2. Group by customer → find customers with repeated problems
  3. Group by time → find patterns (e.g., bugs after deploys)
  4. Track keyword frequency → emerging issues before they become patterns

  state_db(action="get_ticket_analytics", period="7d")
  → Top 5 issue categories
  → Repeat offender customers
  → Average resolution times by category
  → SLA compliance rate

PRODUCT INSIGHTS REPORT (weekly):
  Aggregate support data into actionable product feedback.
  Send to owner and product team.
```

## Output Format

### Support Queue Dashboard

```
SUPPORT QUEUE — {date} {time}
================================

OPEN TICKETS: 12
  P1 (Critical): 1 — API outage for enterprise customer (45 min old)
  P2 (High): 3 — billing issues, partial feature broken
  P3 (Medium): 6 — how-to questions, feature requests
  P4 (Low): 2 — general feedback

SLA STATUS:
  P1: 1/1 within SLA (target: 1hr)
  P2: 3/3 within SLA (target: 4hr)
  P3: 5/6 within SLA (target: 24hr) — 1 approaching deadline
  P4: 2/2 within SLA (target: 48hr)

ESCALATED: 2 tickets (1 to engineering, 1 to owner)
AUTO-RESOLVED: 4 tickets today

ACTIONS NEEDED:
  1. Ticket #847 (P1) — Acme Corp API outage. Engineering investigating. ETA: 30 min.
  2. Ticket #843 (P3) — Approaching SLA deadline. Draft ready, needs send.
```

### Weekly Product Insights

```
SUPPORT INSIGHTS — Week of {date}
=====================================

VOLUME: 47 tickets (up 12% from last week)

TOP ISSUES:
  1. "Can't export data to CSV" — 8 tickets (17%)
     → PATTERN: Feature gap. Customers expect this. Product team notified.

  2. "API rate limiting errors" — 6 tickets (13%)
     → PATTERN: Power users hitting limits. Consider tier-based limits.

  3. "Onboarding confusion on Step 3" — 5 tickets (11%)
     → PATTERN: UX issue. Same step trips up multiple new users.

CUSTOMER HEALTH FLAGS:
  - Acme Corp: 3 tickets this week (up from 0). Investigate.
  - DesignCo: Mentioned competitor in support thread. Churn risk.

RESOLUTION METRICS:
  Avg first response: 2.1 hours (target: <4hr) — GOOD
  Avg resolution: 8.3 hours (target: <24hr) — GOOD
  Auto-resolved: 38% (up from 31%) — IMPROVING
  Satisfaction: 4.2/5 (stable)

RECOMMENDED ACTIONS:
  1. Add CSV export feature — 8 tickets = clear demand signal
  2. Increase API rate limits for Pro tier — reduces 13% of tickets
  3. Redesign onboarding Step 3 — UX friction confirmed
```

## Examples

### Example 1: New Support Email

**Input:** (Automatic) Email from sarah@acme.com: "Our API integration has been returning 500 errors since this morning. This is blocking our production deployment. Please fix ASAP."

**Process:**
1. Classify: Technical Bug, P1 (production blocking + enterprise customer)
2. Enrich: Acme Corp, Tier 1, $120K ARR, renewing in 45 days
3. Check known issues: No known API outage
4. Escalate to engineering immediately
5. Draft response acknowledging the issue
6. Notify owner (high-value customer, churn risk)

**Output:**
Response sent to Sarah within 15 minutes. Engineering notified. Owner pinged on Telegram.

### Example 2: "What are customers complaining about?"

**Input:** "What are customers complaining about this week?"

**Process:**
1. Pull all tickets from last 7 days
2. Categorize and group by issue type
3. Detect patterns and repeat issues
4. Generate product insights report

**Output:** Weekly product insights report with top issues, patterns, and recommendations

### Example 3: Handling a Feature Request

**Input:** Email: "It would be great if I could set up custom webhooks for different event types."

**Process:**
1. Classify: Feature Request, P4
2. Check if already on roadmap: Yes, planned for Q2
3. Check if similar feature exists: Partial — generic webhooks available
4. Draft response with existing feature pointer + roadmap note
5. Log feature request vote in state_db

**Output:**
```
Hi {name},

Thanks for the suggestion! Custom event-type webhooks are actually on our
Q2 roadmap — you're not the first to ask for this.

In the meantime, you can use our generic webhook with event filtering
on your end. Here's the guide: [link]

I'll make sure you're notified when the custom webhooks ship.

Best, {agent_name}
```
