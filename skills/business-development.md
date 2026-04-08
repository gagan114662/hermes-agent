# Business Development

Manages outbound prospecting, lead sourcing, and follow-up tracking for Hermes. Runs autonomously at 2am daily to find new leads and maintain outreach cadences.

## When to Use

- Cron job: 2am daily sourcing run (find 10 new leads, verify, add to pipeline)
- Inbound: process replies from prospects in Gmail
- Manual: "find more leads", "check follow-ups", "update prospect status"

## What You Have Access To

- `reddit_search` / `jina_read` / `web_search` — Lead research
- `browser_navigate` — LinkedIn verification
- `prospect_add` / `prospect_update` / `prospect_list` / `prospect_digest` — Hermes prospect tracker
- `gmail_search` / `gmail_get` / `gmail_reply` — Inbound reply handling
- `sheets_get` / `sheets_append` — Optional Google Sheet tracker (ID: {{BD_SHEET_ID}})
- `send_message` — Telegram alerts to Gagan (chat_id: 8444910202)
- `crm_save` / `crm_log` — CRM notes

## Target Market

**Who:** Small and medium businesses (SMBs) that would benefit from an autonomous AI employee — replacing or augmenting a role like sales rep, customer support agent, or ops coordinator.

**Geography:** Canada and US (prioritize Canada, US is acceptable).

**Signals to look for:**
- Posting job listings for repetitive/process roles (SDR, VA, support rep, data entry)
- Founders or ops leaders complaining about scaling costs
- Communities: r/entrepreneur, r/smallbusiness, r/startups, r/Entrepreneur, local business groups
- Indeed/LinkedIn job posts for roles Hermes could replace

**Exclude:** Enterprise, government, healthcare, legal (compliance-heavy verticals).

## Daily Sourcing Run (2am cron)

### Step 1 — Source 15 candidates

Use reddit_search, web_search, and jina_read to find candidates:
```
reddit_search("hiring virtual assistant OR SDR small business 2026")
reddit_search("automating sales outreach startup")
web_search("SMB Canada hiring sales rep 2026 site:indeed.com OR site:linkedin.com")
```

### Step 2 — Verify each candidate (before adding)

For every candidate:
1. Check their website (jina_read or browser_navigate)
2. Find a real contact: check homepage, Contact, About, Book pages
3. Verify LinkedIn exists
4. Skip if: no real website, placeholder email, enterprise/excluded vertical

### Step 3 — Add verified leads to Hermes prospect tracker

```
prospect_add(
    name="Company Name",
    contact="firstname@company.com",
    source="reddit/web/linkedin",
    notes="Why they're a fit: [reason]",
    next_follow_up="YYYY-MM-DD"  # 2 days from today
)
```

Target: add 10 verified leads per run.

### Step 4 — Check existing follow-up queue

```
prospect_digest()
```

For any prospect with `next_follow_up <= today`:
- Draft a short follow-up (plain text, 2–3 sentences)
- Send via `gmail_send` cc'ing gagan@getfoolish.com
- Update prospect: `prospect_update(id, notes="Follow-up 2 sent YYYY-MM-DD", next_follow_up="YYYY-MM-DD")`

### Step 5 — Report to Gagan via Telegram

```
📊 BD run complete:
• X new leads added
• Y follow-ups sent
• Z prospects awaiting reply
Top new lead: [Company] — [one line why]
```

## Follow-Up Cadence

| Attempt | Timing | Action |
|---------|--------|--------|
| Initial | Day 0 | First outreach email |
| Follow-up 1 | Day 2 | Short bump |
| Follow-up 2 | Day 5 | Value add or different angle |
| Follow-up 3 | Day 7 | Final check-in |
| Stop | — | Mark prospect as "closed/no response" |

Never auto-follow-up on:
- Prospects who replied negatively
- Threads Gagan has taken over
- Sensitive or personal threads

## Inbound Reply Processing

When `gmail_search("from:prospect label:inbox is:unread")` returns results:

1. Read the full thread
2. Check `prospect_list()` for existing record
3. If positive/interested: Telegram alert to Gagan immediately — do NOT reply autonomously
4. If negative/unsubscribe: update prospect status, archive thread, no reply needed
5. If question/clarification: draft reply for Gagan's review, send Telegram with draft

Always update the prospect record before marking the email handled.

## Email Writing Standards

- Plain text only, no HTML
- Single-sentence paragraphs
- Subject line: specific and non-salesy ("AI employee for [Company]'s [role]")
- Always cc gagan@getfoolish.com
- Signature: "Hermes | getfoolish.com"
- Never claim the AI attended meetings in person

## Timezone

America/Vancouver (Pacific). Use YYYY-MM-DD for all dates.
