---
name: saas-warm-leads-engine
description: Autonomous warm-leads engine for founders and operators. Finds ICP-matched buyers daily using intent signals, Google Maps or territory-based sourcing, scores and filters leads, drafts or sends personalized outreach, routes high-intent leads into demos, and tracks which campaigns convert. Triggers on: warm leads, find leads, outbound engine, intent signals, LinkedIn outreach, Google Maps scraping, review mining, lead scoring, book demos, prospecting, daily sourcing.
version: 1.1.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [SaaS, Leads, Outbound, LinkedIn, Prospecting, Google Maps, Reviews, ICP, Intent Signals, Demos, Sales]
    related_skills: [saas-growth-playbook, linkedin-founder-growth]
---

# SaaS Warm Leads Engine

## What This Skill Does

This skill runs the execution layer of SaaS lead generation.

It is designed to:
- find warm leads every day using visible buyer-intent signals
- scrape territory-based prospects from Google Maps and similar local directories when geo lead gen is the right motion
- filter those leads down to the exact ICP instead of broad prospect lists
- score leads using fit + urgency + intent
- generate personalized first-touch outreach, especially for LinkedIn and email-style channels
- route qualified leads toward demos
- track what gets replies, meetings, and revenue so future sourcing improves

Use this after the offer, ICP, and message are at least directionally clear.

This skill can operate in either of these modes:
- **Plan mode**: define the lead engine, sourcing rules, messages, and KPIs
- **Execution mode**: run the daily sourcing + outreach workflow using available tools

This skill supports 2 sourcing motions:
- **SaaS intent mode**: intent-signal discovery from posts, jobs, reviews, launches, and ops triggers
- **Maps/territory mode**: geo-based business sourcing from Google Maps plus contact enrichment, review mining, and route ownership

If the user asks to "run this every day", default to execution mode plus a cron-style recurring workflow.

---

## When to Use

Activate this skill when the user says things like:
- "Find warm leads every day"
- "Run AI outreach that books demos"
- "Set up LinkedIn outbound"
- "Build me an automated lead engine"
- "Find only ICP-matched buyers"
- "What signals should we track for outbound?"
- "Track which outreach gets replies"

Use this skill only when the SaaS already has:
- a reasonably clear ICP
- a usable offer
- at least one credible CTA such as reply, demo, trial, or pilot

If ICP or offer clarity is weak, first use `saas-growth-playbook`.

---

## Required Inputs

Collect or infer these before running:

| Input | What to define |
|---|---|
| Product | What the SaaS does in one line |
| ICP | Buyer role, company type, company size, geography, tech stack if relevant |
| Pain trigger | What event or symptom signals likely buying intent |
| Offer | What the lead is being asked to do: reply, book demo, start pilot, etc. |
| Exclusions | Who to skip entirely |
| Daily volume | Target new leads/day and outreach/day |
| Preferred channels | LinkedIn, email-like outreach, founder content, mixed |
| Proof assets | Case study, testimonial, ROI claim, demo, landing page |
| Reply handling | What counts as warm, hot, disqualified, or nurture |
| Territory rules | Cities, radii, countries, named territories, or rep ownership boundaries |
| Maps mode options | Categories to search, review depth, contact enrichment rules, dedupe rules |
| CRM routing | How leads are assigned by geography, segment, or account owner |
| Call artifacts | Whether voice notes or call recordings should be transcribed and attached |

If these are missing, keep the daily engine conservative and state assumptions clearly.

---

## Core Promise

Run this as a system, not a one-off search:

1. Find leads showing intent
2. Filter out everyone outside the ICP
3. Score and rank the survivors
4. Personalize outreach using why-now signals
5. Track replies, meetings, and sales outcomes
6. Double down on the signals and messages that convert

The goal is not "more leads." The goal is:
- more ICP-matched leads
- more replies from real buyers
- more demos booked
- better attribution on what works

---

## Intent Signals

Use at least 10 intent signals. Weight them by how strongly they imply a buying window.

### High-Intent Signals

- hiring for a role your SaaS replaces, augments, or coordinates
- public complaint about the exact workflow problem you solve
- recent funding, expansion, or hiring burst
- category comparison searches or review-page activity
- new tool rollout, migration, or operational change
- explicit request for process help, automation, or efficiency
- founder or operator posting about bottlenecks, backlog, missed follow-up, or low conversion

### Medium-Intent Signals

- thought leadership or comments around the problem category
- active growth motion where your product removes operational drag
- team size crossing a threshold that makes the problem more painful
- repeated content engagement with adjacent pain topics
- relevant job changes or new leaders inheriting the problem

### Low-Intent Signals

- generic industry interest
- broad topical posting with no sign of urgency
- vanity-fit accounts with no operational pain signal

Never treat low-intent curiosity as equal to buying intent.

---

## ICP Filtering Rules

Only keep leads that match the defined ICP.

Required checks:
- company size is in range
- buyer role can influence or make the decision
- problem is plausible for their business model
- geography matches the sales motion
- company is not on the exclusion list

Common exclusion examples:
- students and job seekers
- agencies if the product is for internal ops teams
- enterprises when the sales motion is SMB / mid-market
- tiny hobby businesses when budget is clearly unavailable
- consultants collecting ideas but not buying software

If a lead has strong intent but weak ICP fit, mark as nurture or discard. Do not contaminate the pipeline.

---

## Lead Scoring Model

Score each lead on 3 dimensions:

| Dimension | Range | What it means |
|---|---|---|
| ICP fit | 0-5 | How closely the lead matches the ideal buyer |
| Intent strength | 0-5 | How strong the visible buying signal is |
| Reachability | 0-3 | How easy it is to contact the lead with a credible personalized message |

### Score Bands

| Total | Classification | Action |
|---|---|---|
| 11-13 | Hot | Prioritize immediately, personalize heavily, route toward demo |
| 8-10 | Warm | Send first-touch outreach in current batch |
| 5-7 | Watchlist | Store and nurture, but do not spend heavy personalization |
| 0-4 | Reject | Skip |

When in doubt, protect pipeline quality over volume.

---

## Data to Save Per Lead

For every kept lead, capture:
- name
- company
- role
- website
- business category
- street address
- city
- region/state
- country
- latitude
- longitude
- territory / route owner
- phone number
- verified email
- social profiles
- review count
- average rating
- top review pain points
- source
- source URL
- why-now trigger
- ICP fit notes
- score
- contact path or outreach path
- message angle used
- status

Use Hermes prospect tracking for this system:
- `prospect_add`
- `prospect_update`
- `prospect_list`
- `prospect_digest`

Target a rich lead record, typically 30+ fields when the source supports it.
Prefer completeness that helps personalization, routing, and attribution over vanity metadata.

Suggested statuses:
- `new`
- `queued`
- `contacted`
- `replied`
- `qualified`
- `demo_booked`
- `nurture`
- `disqualified`

---

## Daily Workflow

### Phase 1 — Source Leads

Run targeted searches around the ICP and intent signals.

Use sources such as:
- LinkedIn company and founder activity
- job listings
- Reddit threads
- review pages
- Google Maps and local business listings
- niche communities
- company websites
- public launch / funding / hiring announcements

Use `web_search`, `jina_read`, `web_extract`, and `browser_navigate` to gather signal.

Never start with broad directories. Start with intent-rich sources.

### Google Maps / Territory Mode

Use this mode when the offer targets local businesses, multi-location operators, field sales teams, or geography-bound lead ownership.

Default workflow:
1. Search Google Maps by category + territory
2. Extract business identity and location data
3. Pull live phone, verified email, website, and social profiles when available
4. Read up to 50 Google reviews to identify recurring pain points, complaints, and buying triggers
5. Cross-reference review pain + business type + your offer
6. Generate one personalized cold email per business
7. Route the lead to the correct territory owner in the CRM

Preferred fields in Maps mode:
- business name
- primary category
- website
- phone number
- verified email
- address
- latitude / longitude
- hours
- rating
- review count
- top review themes
- owner / manager clues
- social profile URLs
- territory / owner
- last contact status

Geography notes:
- support country and territory-aware sourcing wherever the underlying source is accessible
- normalize phone, address, and locale fields for 200+ country-style formats
- do not assume US-only postal, state, or phone conventions

### Phase 2 — Filter and Score

For each candidate:
1. Confirm ICP fit
2. Extract the strongest visible intent signal
3. Estimate reachability
4. In Maps mode, mine reviews and summarize the top operational pain points before scoring
5. Score the lead
6. Add only score-qualified leads to the prospect system

If the source is weak or the profile is ambiguous, do not force it into the pipeline.

### Phase 3 — Personalize Outreach

For each hot or warm lead, draft a personalized opening based on:
- the lead's visible trigger
- the ICP pain
- the promised outcome
- one relevant proof point

In Maps mode, personalization should also use:
- the most common negative review themes
- service gaps or ops complaints repeated across reviews
- geography or territory context when it matters
- local proof points if the offer is region-sensitive

Use this structure:

1. Open with the specific trigger
2. Connect it to the problem your SaaS solves
3. Make one relevant promise
4. Give one clear CTA

Keep first touch short. The goal is reply or booked demo, not a full pitch.

If the workflow is email-first, write one message per business.
Do not mass-template entire batches when the skill has enough signal to personalize.

### Phase 4 — Send or Queue Outreach

Default channel priority:
- LinkedIn DM if the user wants founder-led social selling and access exists
- email-like outreach if a credible contact path exists
- manual review queue when sending authority is unclear

If email sending is enabled:
- send one by one, not as a visible blast
- preserve per-lead personalization
- stagger delivery when the provider or mailbox setup requires conservative pacing
- optimize for inbox placement and trust, not raw volume

If direct automated send is available and approved, send.
If not, draft messages and queue them for fast approval.

Always update the lead record with:
- channel
- message angle
- date sent
- current status
- mailbox / sender identity
- assigned territory owner when applicable

### Phase 5 — Track Responses

Check for:
- replies
- positive replies
- objections
- requests for more info
- booked demos
- no response after a defined interval

Update lead state immediately.

Use outcomes to learn:
- which signals produced replies
- which ICP slices booked demos
- which message angles converted
- which territories or geo clusters convert best
- which review pain points correlate with replies

### Phase 6 — Send Daily Briefing

At the end of each run, send a concise owner update summarizing:
- leads found
- leads contacted
- replies received
- demos booked
- top-performing intent signals
- top-performing message angles
- recommendations for tomorrow

Use `send_message` for the daily briefing when available.

---

## Outreach Rules

### Personalization Rules

Every first-touch message must include at least one of:
- a visible hiring signal
- a recent founder or company post
- a workflow pain clue
- a specific growth or ops trigger

Do not use generic fake-personalization such as:
- "Loved what you're building"
- "Saw your impressive company"
- "Thought I'd reach out"

### CTA Rules

Use one CTA only:
- reply with interest
- book a demo
- confirm whether the problem is active

Do not stack multiple asks in the first message.

### Volume Rules

Do not optimize for maximum send volume. Optimize for:
- ICP purity
- signal quality
- relevance of angle
- reply quality

If quality falls, reduce volume and tighten filters.

---

## Demo Booking Rules

Use these defaults for response handling:

| Response Type | Action |
|---|---|
| Positive interest | move to `qualified` and propose a demo |
| Direct availability request | move to `demo_booked` workflow |
| Curious but vague | ask one qualifying question |
| "Not now" | move to `nurture` with later follow-up |
| No fit | move to `disqualified` and log reason |

Hot leads should get fast handoff and minimal friction.

If the lead qualifies, route toward:
- a lightweight booking link
- a founder-led 1:1 demo
- a short qualification call first

Match the demo motion to fit and urgency.

---

## Tracking and Optimization

Track the system at 3 levels:

### 1. Signal Level
- which intent signals produced replies
- which signals produced demos
- which signals produced low-quality leads

### 2. Campaign Level
- outreach angle used
- source channel
- reply rate
- qualification rate
- demo-book rate

### 3. ICP Slice Level
- role
- company size
- industry
- geography

Use these to produce an answer to:
"What should we do more of tomorrow?"

### Territory and CRM Routing

When geo matters, maintain a GPS-aware CRM view:
- store latitude and longitude on each lead when available
- assign by territory, radius, city cluster, or named owner
- prevent duplicate outreach across adjacent territories
- preserve route ownership in every lead update and summary

If voice notes or call recordings are present, transcribe them and attach:
- key objections
- urgency signals
- buying timeline
- next-step commitments

---

## Metrics That Matter

Track these daily and weekly:

| Metric | Why it matters |
|---|---|
| New qualified leads added | Pipeline quality and sourcing consistency |
| Outreach sent | Throughput |
| Reply rate | Message-market resonance |
| Positive reply rate | Real buyer interest |
| Demo-book rate | Sales readiness |
| Qualified-to-demo conversion | Lead quality |
| Sales or pilots sourced | Revenue signal |

Do not celebrate impressions, profile views, or list size unless they correlate with meetings or sales.

---

## Recommended Daily Output

When this skill runs, produce:

### 1. Sourcing Summary
- number of leads reviewed
- number kept
- number rejected

### 2. Lead Batch
- top hot leads
- top warm leads
- why each lead made the cut

### 3. Outreach Summary
- messages sent or queued
- angles used
- CTA used

### 4. Conversion Summary
- replies
- positive replies
- demos booked

### 5. Learnings
- best signal today
- best message angle today
- what to change tomorrow

---

## Automation Pattern

If the user wants this to run every day, use this pattern:

1. Morning or overnight sourcing run
2. Daily brief to the owner
3. Separate reply-processing pass later in the day
4. Weekly review of which signals and campaigns are converting

If scheduling is available, use a recurring cron-style workflow.
If not, still define the exact recurring cadence in the plan.

---

## Guardrails

Do not:
- add non-ICP leads just to fill a quota
- send generic spam
- over-personalize low-value leads at the expense of throughput
- auto-send if permissions or delivery path are unclear
- claim results or proof the product does not have
- move weak leads into high-touch demo flows too early

If outreach tooling is unavailable, downgrade gracefully to:
- lead scoring
- message drafting
- owner review queue
- daily recommended next actions

---

## Verification

This skill is working when:
- leads added each day are tightly ICP-matched
- every kept lead has a real why-now trigger
- outreach uses the trigger instead of generic copy
- reply and demo metrics are logged consistently
- the owner can clearly see which signals and campaigns convert
- the system improves lead quality over time instead of just increasing send volume

If the system produces lots of contacts but few qualified replies, tighten ICP rules and signal thresholds before increasing volume.
