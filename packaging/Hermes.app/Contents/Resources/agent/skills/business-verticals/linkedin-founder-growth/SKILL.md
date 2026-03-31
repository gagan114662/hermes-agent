---
name: linkedin-founder-growth
description: LinkedIn personal brand engine for founders and B2B sellers. Optimizes profile for ICP, builds daily content around buyer problems, drops lead magnets, runs opt-in email sequences, and tracks what drives inbound — then doubles down. Triggers on: LinkedIn, personal brand, founder content, B2B leads, ICP, lead magnet, inbound, profile optimization, thought leadership.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [LinkedIn, Founder, B2B, Lead Generation, Content, Personal Brand]
---

# LinkedIn Founder-Led Growth Skill

## What This Skill Does

This skill turns LinkedIn into a repeatable inbound pipeline for founders and B2B sellers. It covers six execution pillars — profile optimization, content strategy, lead magnets, email sequences, tracking, and daily execution — all oriented around the buyer's problems, not the seller's features.

Run this skill to:
- Audit and rewrite a LinkedIn profile so the ICP immediately understands what you do and why it matters to them
- Build and execute a weekly content calendar that positions the founder as the expert buyers want to call
- Drop lead magnets twice a week and route opt-ins into a 3-email sequence that ends in a booked call
- Track what is working and systematically double down on the formats and topics that drive inbound

---

## Pillar 1: Profile Optimization (ICP-First)

The profile is the landing page. Before any content works, the profile must convert visitors into followers and followers into opt-ins.

### Audit Checklist (run monthly, and whenever the offer changes)

Run `web_search` on your own name + industry to see how you appear in search. Then audit each element:

- [ ] Headline speaks to ICP pain and result — not your job title
- [ ] Banner has one clear visual message aligned to what the ICP wants
- [ ] About section opens with a hook, not "I am..."
- [ ] Featured section has your best lead magnet or case study pinned (not your company website)
- [ ] Recent posts are visible and on-brand
- [ ] Contact info is visible and up to date
- [ ] 500+ connections (credibility signal)
- [ ] Creator mode is ON (enables Follow button and LinkedIn newsletter feature)
- [ ] Profile URL is customized (first-last or brand name, not the default random string)

### Headline Formula

Do not use your job title. Use this formula:

```
[Who you help] + [Result you deliver] + [How / differentiator]
```

Examples:
- "I help B2B SaaS founders book 10+ qualified calls/month — without cold outbound"
- "Helping DTC brands cut CAC 30% using email — not more ad spend"
- "I turn founder expertise into inbound pipeline on LinkedIn — content + systems"

### About Section Structure

| Section | Purpose | Length |
|---|---|---|
| Hook | Open with a pain the ICP recognizes immediately | 1–2 lines |
| Story | Why you understand this problem (your experience, not credentials) | 2–3 lines |
| Proof | Specific results you have delivered (numbers, names, outcomes) | 2–3 lines |
| CTA | Tell them exactly what to do next (DM, grab lead magnet, book a call) | 1 line |

Never start with "I am a..." — start with the pain.

### Featured Section

Pin exactly one thing: your highest-converting lead magnet or your best case study. This is the one action you want profile visitors to take. A link to your company homepage is a wasted slot.

### Banner

One message. One visual. The message should show the ICP the result they want — not your logo, not your tagline, not a stock photo. If someone reads only the banner, they should know what you do and who it is for.

### Research Tools

Use these before writing or rewriting any profile element:

| Task | Tool | Query |
|---|---|---|
| Find the words ICP uses to describe their pain | `web_search` | "[ICP role] biggest challenges 2026" |
| Find pain language in forums | `web_search` | "site:reddit.com [ICP industry] problems" |
| Analyze top-performing competitor profiles | `jina_read` | Profile URLs of 3–5 top voices in your niche |

Mirror the ICP's language back to them. If they say "we're drowning in leads we can't qualify," your headline should include language about qualification — not "pipeline efficiency."

---

## Pillar 2: Content Strategy (Buyer Problems, Not Features)

Every post should make the ICP feel understood. Never post product features. Post the problems your buyers wake up thinking about, and show that you understand those problems better than anyone else.

### Weekly Content Calendar

| Day | Content Type | Format | Goal |
|---|---|---|---|
| Monday | Authority content | Long-form post (500–800 words) | Position as the expert |
| Tuesday | Lead magnet drop | Post + comment with link | Drive opt-ins |
| Wednesday | Strong opinion / hot take | Short punchy post (150–250 words) | Engagement and shares |
| Thursday | Results / proof | Before/after, case study, testimonial | Build trust |
| Friday | Lead magnet drop | Carousel or checklist | Drive opt-ins |
| Saturday | Behind the scenes / founder story | Short authentic post | Humanize the brand |
| Sunday | Engage only | Comment on 20 posts from ICP | Build visibility in feed |

### Content Angle Research (run every Sunday)

Pull fresh angles before planning the week:

```
web_search: "[ICP role] biggest challenges 2026"
web_search: "site:reddit.com [ICP industry] problems"
web_search: "[competitor name] reviews what people hate"
jina_read: top-performing posts in your niche — identify which hooks are working
```

### Hook Formulas (rotate weekly)

The hook is the first line. It is the only thing that determines whether someone keeps reading. Use these formulas and rotate them so the feed does not go stale:

```
"Most [ICP role]s are doing [X] wrong. Here's what actually works:"
"I [result] in [timeframe]. Here's the exact playbook:"
"Unpopular opinion: [contrarian take on the industry]"
"[Number] things I wish someone told me before [experience]:"
"The reason your [X] isn't working (it's not what you think):"
"I asked 50 [ICP roles] their biggest problem. This one came up every time:"
"[Specific result] without [common pain/sacrifice]:"
"We went from [bad state] to [good state] in [timeframe]. Here's what changed:"
```

---

## Pillar 3: Lead Magnets (2x/week)

Lead magnets are the mechanism that converts post readers into email subscribers. Drop them on Tuesday and Friday, every week, without exception.

### Formats That Convert on LinkedIn

| Format | Template |
|---|---|
| Checklist | "The [X]-point checklist for [ICP goal]" |
| Template | "The exact [document type] we use for [result]" |
| Mini-guide | "How to [achieve outcome] in [timeframe]" |
| Calculator / scorecard | "Find out your [metric] score in 2 minutes" |
| Swipe file | "The [X] scripts/emails/templates that got us [result]" |

### Lead Magnet Post Format

```
[Hook — name the pain clearly]

[1–2 lines proving you understand it deeply — specific, not generic]

I built a [format] that solves this.

It covers:
✅ [Benefit 1]
✅ [Benefit 2]
✅ [Benefit 3]

Drop "SEND" in the comments and I'll DM it to you.

[Optional: share one insight from it to prove it is real and valuable]
```

### Automation Workflow

When someone comments "SEND":

1. Auto-DM the lead magnet link via LinkedIn MCP / `send_message`
2. Add contact to email sequence (see Pillar 4)
3. Call `prospect_add` with `source=linkedin_magnet`

Never send the lead magnet without completing all three steps. The magnet is the top of funnel — the sequence is what converts.

---

## Pillar 4: Email Sequences (3-Email Opt-In Sequence)

Every lead magnet opt-in enters this sequence automatically. The sequence delivers value, builds trust, and ends with a direct ask to book a call.

### Email 1 — Deliver + Quick Win (send immediately)

- **Subject:** "Here's your [lead magnet name]"
- **Body:** Deliver the resource. Give one actionable tip they can use today — something not in the document, to over-deliver.
- **CTA:** "Reply and tell me your #1 challenge with [topic]"

Replies to Email 1 trigger segmentation. Flag as hot lead. Call `prospect_add` with high priority. Reach out within 24 hours.

### Email 2 — Deeper Value (send Day 3)

- **Subject:** "[Problem] — here's what actually works"
- **Body:** Expand on one key insight from the lead magnet. Use a real example or story. Make it feel like a private lesson, not a newsletter.
- **CTA:** "Here's a case study showing this in action" → link to relevant content

### Email 3 — CTA to Book (send Day 7)

- **Subject:** "Can I show you how this works for [their company type]?"
- **Body:** Short and direct.

```
You downloaded [X], which tells me you're dealing with [problem].

We help [ICP] achieve [result] in [timeframe].

If you want to see if we're a fit, grab 20 minutes here: [calendar link]
```

- **CTA:** Book a call

### Sequence Metrics and Thresholds

| Metric | Target | Action If Below Target |
|---|---|---|
| Email 1 open rate | >40% | Test a new subject line |
| Email 2 click rate | >8% | Rewrite the CTA or case study link |
| Email 3 reply rate | >3% | Personalize the subject line |
| Email 3 book rate | >1% | Shorten the email, make the CTA more direct |

---

## Pillar 5: Tracking and Doubling Down

What gets tracked gets improved. Pull these metrics every Monday morning before planning the week.

### Weekly Metrics Dashboard

| Metric | Source | Target |
|---|---|---|
| Profile views | LinkedIn Analytics | Growing week-over-week |
| Search appearances | LinkedIn Analytics | Growing week-over-week |
| Post impressions | LinkedIn Analytics | >1,000 per post average |
| Follower growth | LinkedIn Analytics | >50/week |
| Lead magnet opt-ins | Email platform | >20/week |
| Email sequence books | Calendar | >3/week |
| Inbound DMs | LinkedIn inbox | Track source for each |

### Weekly Analysis (4 questions)

1. Which post got the most impressions? Identify the format, topic, and hook. Write 3 variations for next week.
2. Which lead magnet got the most opt-ins? Create a sequel or expand it into a longer guide.
3. Which email got the most replies? Use that angle for next week's content.
4. Where are inbound DMs coming from? Which post topic, lead magnet, or keyword is driving them? Double down on that.

### Virality Protocol (post exceeds 5,000 impressions)

When a post hits 5K+ impressions, immediately execute the following:

- Repurpose as a LinkedIn carousel (same content, visual format)
- Turn into a Twitter/X thread
- Extract key quote for Instagram or TikTok
- Send to email list as a "quick insight" email
- Write a follow-up post: "You resonated with [X] — here's the deeper version:"

Do not wait. Momentum from a high-performing post decays within 48 hours.

---

## Pillar 6: Daily Execution Checklist

Consistency beats virality. The goal is to show up every day and make it easy for the ICP to find you, follow you, and reach out.

### Morning Block (9am — 20 minutes)

- [ ] Post today's content (draft already queued from Sunday planning session)
- [ ] Check notifications — reply to ALL comments within 1 hour of posting (first-hour engagement is the strongest algorithmic signal)
- [ ] Send lead magnet DMs to anyone who commented "SEND" yesterday

### Afternoon Block (1pm — 15 minutes)

- [ ] Engage on 10–15 posts from ICP accounts (add value in comments — insight, question, or specific observation — never "great post")
- [ ] Check DM inbox — respond to all, log warm leads via `prospect_add`

### Evening Block (5pm — 10 minutes)

- [ ] Review today's post performance (impressions, comments, follows gained)
- [ ] Queue tomorrow's post if not already done
- [ ] Check email sequence metrics — flag any hot replies for follow-up

---

## Sunday Content Planning Session (30 minutes)

Run this every Sunday before the week starts. This is what makes daily execution fast and low-friction.

1. Pull last week's analytics — identify what worked
2. Pick 7 content angles for the week: 2 lead magnet drops + 5 content posts
3. Write all 7 posts in one session using the hook formulas above
4. Schedule via LinkedIn native scheduler or Buffer/Hootsuite MCP
5. Prepare lead magnet CTAs for Tuesday and Friday posts

Batch creation prevents the daily scramble that leads to skipped posts and inconsistent output.

---

## Tools Reference

| Task | Tool |
|---|---|
| ICP research and pain language | `web_search`, `jina_read` |
| Content writing | LLM (write directly) |
| Lead magnet DMs | LinkedIn MCP / `send_message` |
| Email sequences | Gmail MCP + `send_email` |
| Lead capture | `prospect_add` |
| Analytics tracking | `web_search` + LinkedIn Analytics MCP |
| Post scheduling | Buffer/Hootsuite MCP or LinkedIn native scheduler |
| Owner alerts and weekly report | `send_message` (Telegram) |

---

## Weekly Report (every Monday via Telegram)

```
LinkedIn Weekly — [date range]

Profile views: [X] (+/-% vs last week)
Search appearances: [X]
Top post: [hook] — [X] impressions, [X] engagements
Followers gained: [X] (total: [X])

Lead magnet opt-ins: [X]
Email sequence books: [X]
Hot inbound DMs: [X]

What worked: [format / topic / hook]
Double down on: [specific angle or format]

This week's content plan: [brief summary of 7 angles]
```

---

## What You Never Do

These are non-negotiable. Violating any of them degrades the system over time.

- **Never pitch in the first DM.** Lead with value. Always. The first DM is for delivering the lead magnet or starting a conversation, not selling.
- **Never post product features.** Post buyer problems and outcomes. The ICP does not care about your features — they care about their results.
- **Never use 30 hashtags.** Use 3–5 relevant, specific hashtags per post. More than that looks like spam and LinkedIn's algorithm treats it accordingly.
- **Never automate connection requests with generic messages.** Personalize every request. One sentence referencing something real about their work is enough.
- **Never ignore a comment.** Every comment boosts reach and is a potential lead. Reply to every single one, especially in the first hour.
- **Never go dark for more than 2 days.** Consistency beats viral posts. An average post every day outperforms an incredible post once a month.
- **Never send a lead magnet without adding to the email sequence.** The magnet without the sequence is a dead end. The sequence is where conversion happens.
- **Never book a call without qualifying the lead first.** Wrong-fit calls waste time for both sides and create bad experiences. Qualify in DM before sending the calendar link.
