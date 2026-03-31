# AI Employee SaaS — Design Document

**Date:** 2026-03-30
**Status:** Approved

---

## What We're Building

An AI employee-as-a-service platform. Customers pay $299/month to get a fully autonomous AI employee that handles their sales, marketing, and customer support — with a real phone number, a face, and 24/7 availability.

The AI employee is powered by Hermes + OpenWork on a dedicated VM per customer.

---

## Product

### What the customer gets

- **Phone number** — Vapi.ai handles inbound + outbound calls in the customer's business voice
- **Face** — HeyGen streaming avatar for async video messages and video calls
- **Text/WhatsApp** — Twilio for SMS outreach and support
- **24/7 operation** — Cron-driven outreach, follow-ups, reports
- **Business memory** — Remembers every customer, deal, and interaction
- **Self-configuring** — Onboards itself by interviewing the customer over Telegram

### What the AI employee does

| Job | How |
|---|---|
| Answer inbound calls | Vapi webhook → Hermes (business context loaded) |
| Make outbound sales calls | Hermes cron → Vapi outbound API |
| Send follow-up SMS | Hermes cron → Twilio |
| Research prospects | Hermes reach tools (LinkedIn/Reddit/RSS) |
| Post social content | Hermes cron → Twitter/LinkedIn tools |
| Handle customer support | Telegram/WhatsApp gateway |
| Send weekly report to owner | Hermes cron → Telegram message |
| Record async video updates | HeyGen API → delivered via Telegram/email |

---

## Architecture

### Control Plane (single server — your VPS)

Manages all customers. Responsibilities:
- Runs the onboarding Telegram bot
- Provisions/teardowns customer VMs via DigitalOcean API
- Manages Stripe subscriptions
- Routes Vapi webhooks to correct customer VM
- Monitors VM health

**Stack:** Python + Hermes gateway + DigitalOcean API + Stripe API + Cloudflare

### Per-Customer VM (DigitalOcean $12/mo droplet)

One VM per paying customer. Fully isolated.

```
VM contents:
├── Hermes (brain + memory + tools + cron + gateway)
├── OpenWork (workflow orchestration)
├── Vapi webhook server (receives call events)
├── Customer config (business name, industry, persona, contacts)
└── Nginx (routes inbound webhooks)
```

**VM spec:** 2 vCPU / 2GB RAM / Ubuntu 22.04 (sufficient for Hermes + OpenWork)

### Onboarding Flow

```
Customer signs up on landing page
        ↓
Stripe payment confirmed → webhook to control plane
        ↓
Control plane sends Telegram message: "Hi! I'm setting up your AI employee.
Let me ask you a few questions..."
        ↓
Hermes interviews customer over Telegram (10 questions):
  - Business name + what you sell
  - Target customer (who buys from you)
  - Your tone (professional/casual/friendly)
  - Existing customers to import (CSV optional)
  - Goals (more leads / better support / both)
  - Hours of operation
  - Name for your AI employee
        ↓
Control plane provisions VM via DigitalOcean API
        ↓
VM boots, Hermes + OpenWork install, config written
        ↓
Vapi phone number purchased + webhook pointed at VM
        ↓
Customer receives: phone number, HeyGen avatar link, Telegram handle
        ↓
AI employee is live
```

---

## Tech Stack

| Component | Tool | Cost/mo |
|---|---|---|
| AI brain | Hermes (self-hosted) | $0 |
| Workflow engine | OpenWork (self-hosted) | $0 |
| Voice calls | Vapi.ai | ~$30 (600 min avg) |
| Phone number | Vapi/Twilio | ~$2 |
| SMS/WhatsApp | Twilio | ~$5 |
| Video avatar | HeyGen API | ~$29 (starter) |
| Outbound email | Resend | ~$0 (free tier) |
| VM per customer | DigitalOcean | $12 |
| VM provisioning | DigitalOcean API | $0 |
| Billing | Stripe | 2.9% + $0.30 |
| DNS/routing | Cloudflare | $0 |
| Landing page | Simple HTML on Cloudflare Pages | $0 |
| **Total COGS** | | **~$78/customer/mo** |
| **Revenue** | $299/mo | |
| **Gross margin** | | **~74%** |

---

## Implementation Phases

### Phase 1 — Core infrastructure (build first)
1. Control plane server with DigitalOcean VM provisioning API
2. Stripe webhook → VM provision trigger
3. Per-customer Hermes + OpenWork VM setup script (automated)
4. Vapi integration on Hermes (voice tool)
5. HeyGen integration on Hermes (avatar tool)
6. Twilio SMS integration on Hermes

### Phase 2 — Onboarding
7. Onboarding Telegram bot (interviews customer, writes config)
8. Auto-deploys customer config to their VM
9. Purchases Vapi phone number, configures webhook
10. Delivers credentials to customer

### Phase 3 — Business automation
11. Sales cron: daily prospect research + outreach
12. Follow-up cron: SMS/email sequences
13. Weekly report cron: business summary to owner
14. Social posting cron: Twitter/LinkedIn content

### Phase 4 — Go to market (the business sells itself)
15. Landing page (Cloudflare Pages)
16. The AI employee markets itself (uses its own tools to generate leads for you)
17. Demo video (HeyGen avatar explains the product)

---

## Revenue Model

- **Price:** $299/month per AI employee
- **COGS:** ~$78/month
- **Gross margin:** ~74%
- **Break-even:** 1 customer covers infra + Vapi costs
- **10 customers:** ~$2,210/mo profit
- **100 customers:** ~$22,100/mo profit

---

## Key Decisions

1. **VM per customer** — full isolation, no shared state risk, easy to debug
2. **DigitalOcean** — simple API, predictable pricing, fast spin-up (~55s)
3. **Vapi over VibeVoice** — VibeVoice is research-only with no phone support; Vapi is production-hardened
4. **Hermes as brain** — already has memory, cron, tools, Telegram gateway, reach tools
5. **OpenWork for workflows** — adds composable process management on top of Hermes
6. **Self-onboarding** — Telegram interview means zero manual work per customer
