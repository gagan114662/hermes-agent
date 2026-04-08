# Hermes Delight Onboarding — Design Doc

**Goal:** Business owner installs a desktop app, grants one permission, and within 5 minutes Hermes has connected to all their tools and is already working — without being asked a single question.

**Core principle:** Hermes is a proactive worker, not a chatbot. It acts first, reports after.

---

## The First 5 Minutes

### T+0 — Install
One `.dmg`. Drags to Applications. Opens to a single screen:

> "Hermes needs one permission to run your business. This gives it access to your tools, accounts, and email — on your machine only, never uploaded."

One button: **"Trust Hermes"**

Grants: Keychain, Full Disk Access, Accessibility, Mail, Calendar, Contacts.

### T+30s — Silent Scan
No loading screen. No setup wizard. Hermes scans:
- macOS Keychain → every saved credential
- Chrome/Safari cookies → every active logged-in session
- Running apps → QuickBooks open? Shopify tab? Gmail?
- Maps each credential → spins up MCP server for that tool automatically

### T+2min — First Telegram message (unprompted)
> "Hi [name] 👋 I'm already working. I connected to 11 of your tools. Give me 3 minutes."

No response needed.

### T+5min — The Wow Report
> Here's what I just did:
> ✅ Replied to 3 unanswered customer emails in your tone
> ✅ Found 2 people on Reddit asking about [business type] — sent DMs
> ✅ Sent a payment reminder to David Chen ($1,200 overdue 14 days)
> ✅ Rescheduled your missed call with Jake Miller for tomorrow 10am
>
> I'll keep going. I'll update you every morning.

Owner never typed a single command.

---

## The Ongoing Loop (every 15 min, forever)

| Queue | Hermes watches | Hermes does |
|---|---|---|
| Inbox | Unanswered emails > 2hrs | Replies in owner's voice |
| Leads | No follow-up in 3 days | Sends SMS/email/DM |
| Money | Invoices overdue | Sends reminder, logs in CRM |
| Reputation | New Google/Yelp review | Responds publicly |
| Prospecting | Reddit/Maps pain posts | Adds to pipeline, outreaches |

All silent. Owner only sees the morning summary on Telegram.

---

## Credential → Tool Connection Flow

```
Keychain / Browser saved passwords / Active cookies
      ↓
  Detect service (gmail.com, shopify.com, quickbooks.com...)
      ↓
  Match → MCP server config template
      ↓
  Spin up MCP server with credentials
      ↓
  Verify connection (one test API call)
      ↓
  Add to Hermes toolset live (no restart needed)
```

Credentials never leave the machine. VM only gets the MCP tool interface.

---

## Menubar App

Tiny icon in macOS menu bar. One click shows live feed:

```
● Hermes is working
─────────────────────────────
2 min ago   Replied to Maria G. (customer email)
8 min ago   Sent follow-up to Jake Miller
15 min ago  Connected to QuickBooks ✓
─────────────────────────────
[Pause]   [View All Activity]
```

Owner feels like watching an employee work through a glass wall.

---

## Components to Build

1. **macOS desktop app** — Electron or Swift, requests all permissions upfront, launches Hermes gateway as background service, keeps Cloudflare tunnel alive
2. **Credential harvester** — reads Keychain + browser passwords/cookies, maps to known services, never sends off-device
3. **MCP auto-configurator** — for each detected service, picks the right MCP server template, spins it up, verifies, adds to toolset
4. **Proactive work loop** — 15-min cron that checks all 5 queues and acts without asking
5. **Morning digest** — daily Telegram summary of everything Hermes did
6. **Menubar app** — live activity feed, pause/resume toggle

---

## Target Services for Auto-Detection (v1)

Gmail, Google Calendar, Google Drive, Shopify, QuickBooks, Xero, HubSpot, Calendly, Stripe, Square, Notion, Airtable, Slack, Trello, WooCommerce, Yelp, Google My Business
