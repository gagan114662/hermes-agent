---
name: customer-acquisition
description: Daily automated customer acquisition for the AI employee SaaS. Researches prospects across job boards, Reddit, and Google Maps. Scores and batches them for owner approval.
version: 1.0.0
---

# Customer Acquisition Skill

You are hunting for small business owners who need an AI employee. Target: businesses actively hiring sales/support staff (they have budget + proven need) OR businesses losing customers due to missed calls.

## Channel 1 — Job Listing Research (highest intent)

Small businesses posting jobs for sales/support roles have PROVEN budget and PROVEN need. This is the highest-value channel.

Search for recent job postings:
```
web_search("site:indeed.com \"sales representative\" OR \"customer service\" posted:today small business")
web_search("\"appointment setter\" OR \"sales rep\" indeed.com small business -enterprise posted:1d")
```

For each listing found:
1. Extract: company name, job title, location
2. Visit their website via `jina_read` to find phone/email/industry
3. Score (1–10): start at 5, +2 if hiring sales rep, +1 if hiring customer service, +1 if company size < 50, +1 if local business (not remote-only)
4. Add: `prospect_add(name=company, source="indeed", pain_point="Hiring [role] — has budget for staff", contact_hint=website_contact, score=score)`

## Channel 2 — Reddit Pain Research

Search for business owners expressing the exact problems we solve:
```
reddit_search("overwhelmed missing calls losing sales", subreddit="smallbusiness")
reddit_search("can't keep up need help answering phones", subreddit="entrepreneur")
reddit_search("need someone to follow up leads sales", subreddit="ecommerce")
```

For each relevant post (pain clearly described, sounds like a business owner):
1. Score: +3 if mentions losing revenue, +2 if mentions budget, +1 per pain keyword match
2. Add: `prospect_add(name=username+" (Reddit)", source="reddit", source_url=post_url, pain_point=post_title[:120], contact_hint="u/"+username, score=score)`

## Channel 3 — Google Maps Pain Research

Find businesses with reviews complaining about missed calls:
```
web_search("\"never called back\" OR \"goes to voicemail\" \"small business\" reviews 2024 2025")
web_search("plumber OR electrician OR dentist \"missed my call\" OR \"no answer\" reviews")
```

For each business found:
1. Get their phone via `jina_read` on their Google Maps/Yelp page
2. Score: +4 if reviews explicitly mention missed calls
3. Add: `prospect_add(name=business_name, source="maps", pain_point="Reviews: missed calls/voicemail complaints", contact_hint=phone_number, score=score)`

## Daily Digest

After research (aim for 10+ new prospects):
1. Generate digest: `prospect_digest(limit=10)`
2. Send to owner: `send_message(platform="telegram", message=digest_text)`

## After Owner Approves

When owner replies "APPROVE ALL" or "APPROVE 1,3,5":
1. Parse which prospects to contact
2. For Reddit: use `browser_navigate` to compose a DM
3. For Indeed/Maps: use `sms_send` or `web_extract` to find email + send via `send_message`
4. Outreach template:
   "Hey [name], saw you're [pain_point]. I built an AI employee that answers calls, does follow-up SMS, and researches prospects — 24/7 for $299/mo. Want a free 7-day trial?"
5. Update: `prospect_update(prospect_id=pid, status="contacted", notes="Sent DM via [channel]")`

## Weekly Content Posts

Post 3x/week to drive inbound leads:
- Draft post: "I built an AI employee that handles calls+SMS for $299/mo. Drop your number and it'll call you in 60 seconds to demo itself."
- Post to r/entrepreneur, r/smallbusiness, or r/ecommerce via `browser_navigate`
- Any replies → `prospect_add` with source="reddit_inbound"
