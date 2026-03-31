# Meeting Intelligence

## Purpose

Full-lifecycle meeting support: research attendees before meetings, prepare briefing documents with talking points, process meeting notes afterward, extract action items, and draft follow-up communications. Turn every meeting into a well-prepared, well-documented interaction.

## When to Use

Activate this skill when:
- User says "prep me for my meeting with [person/company]"
- User says "research [attendee name] before our call"
- User says "brief me on who I'm meeting today"
- A calendar event is coming up in the next 30 minutes (auto-trigger)
- User shares meeting notes or transcript after a call
- User says "send follow-up", "what were the action items", "summarize that meeting"
- User says "what do we know about [person]"
- Daily morning briefing includes upcoming meeting prep

## What You Need

### Tools
- `web_search` — Research attendees, companies, recent news, industry context
- `web_extract` — Pull detailed content from LinkedIn profiles, company pages, news articles
- `read_file` — Load prior meeting notes, CRM data, email threads with attendees
- `write_file` — Save briefing docs, meeting summaries, action item logs
- `send_message` — Deliver briefings to owner, send follow-up emails to attendees
- `search_files` — Find prior interactions, proposals, contracts related to attendees
- `calendar_read` — Pull meeting details, attendee list, agenda
- `prospect_tool` — Check CRM for relationship history, deal stage, customer tier
- `browser_navigate` — Access LinkedIn profiles, company websites, news articles
- `state_db` — Store meeting intelligence, track action items across meetings

### Data Needed
- Meeting details: title, time, attendees, agenda (from calendar)
- Attendee names and email addresses
- Prior meeting notes and email threads with these people
- CRM relationship data (deal stage, tier, last interaction)
- Owner's goals for the meeting (if provided)

---

## Pre-Meeting: Research & Briefing

### Step 1: Gather Meeting Context

When a meeting is approaching or the owner asks for prep:

```
1. Pull meeting details from calendar:
   calendar_read(event_id=target_meeting)
   → Extract: title, attendees (names + emails), agenda, description, location/link

2. Identify what kind of meeting this is:
   - Sales/prospect call → focus on company research, BANT qualification, deal history
   - Customer check-in → focus on account health, open tickets, renewal dates
   - Investor meeting → focus on metrics they care about, recent portfolio news
   - Internal sync → focus on project status, blockers, prior action items
   - Partnership discussion → focus on mutual value, competitor landscape
   - Cold/new meeting → focus heavily on attendee research (you know nothing yet)

3. Check what we already know:
   search_files(query=attendee_name OR attendee_company)
   read_file("meetings/[related_topic]/*.md")
   prospect_tool(action="search", query=attendee_email)
```

### Step 2: Research Each Attendee

For every external attendee, build an intelligence profile:

```
1. LinkedIn research:
   web_search(query="{attendee_name} LinkedIn {company_name}")
   web_extract(url=linkedin_profile_url)
   → Extract: current title, tenure, career history, recent posts, mutual connections

2. Company research:
   web_search(query="{company_name} recent news funding")
   web_extract(url=company_website)
   → Extract: company size, funding stage, recent announcements, product/service overview

3. Recent activity and news:
   web_search(query="{attendee_name} {company_name} 2026")
   → Extract: recent talks, blog posts, interviews, press mentions

4. Social signals:
   web_search(query="{attendee_name} twitter OR podcast OR conference")
   → Extract: topics they care about, opinions expressed publicly, speaking engagements

5. Shared connections and context:
   web_search(query="{attendee_name} {owner_name_or_company}")
   → Extract: any prior public interaction, mutual contacts, shared events
```

For each attendee, compile:
- **Name and title** — current role, how long in role
- **Background** — career trajectory, notable prior companies
- **Company context** — what the company does, stage, recent news
- **Communication style** — formal/casual (infer from LinkedIn posts, public appearances)
- **Topics they care about** — based on recent posts, talks, articles
- **Potential rapport builders** — shared interests, mutual connections, common background
- **Red flags** — recent layoffs at their company, negative press, competitive tensions

### Step 3: Check Relationship History

```
1. CRM lookup:
   prospect_tool(action="search", query=attendee_email)
   → Deal stage, customer tier, lifetime value, last interaction, notes

2. Email history:
   search_files(query="from:{attendee_email} OR to:{attendee_email}")
   → Recent threads, open questions, promises made by either side

3. Prior meeting notes:
   search_files(query="{attendee_name} meeting notes")
   read_file(matching_files)
   → Previous decisions, action items, unresolved issues

4. Open commitments:
   search_files(query="{attendee_name} action item OR promise OR deadline")
   → What have we committed to? What have they committed to? What is overdue?
```

### Step 4: Prepare Talking Points

Based on all gathered intelligence, generate context-aware talking points:

```
TALKING POINT CATEGORIES:

1. OPENER (rapport building)
   - Reference something specific: recent news, their LinkedIn post, shared connection
   - "I saw your company just [achievement]. Congratulations."
   - "Your post about [topic] resonated — we've been thinking about that too."

2. AGENDA ALIGNMENT (first 2 minutes)
   - Confirm the meeting purpose
   - Propose structure: "I thought we could cover X, Y, Z — does that work?"
   - Set time expectations

3. KEY DISCUSSION POINTS (body of meeting)
   - For each agenda item, prepare:
     a. Your position / what you want to communicate
     b. Questions to ask them
     c. Data points or examples to reference
     d. Potential objections and how to address them

4. SENSITIVE TOPICS (handle with care)
   - Overdue commitments from either side
   - Pricing or contract negotiations
   - Competitor mentions
   - Bad news delivery

5. ASK / CLOSE (what you want from this meeting)
   - Clear desired outcome: decision, next step, commitment, information
   - Fallback ask if primary ask doesn't land
   - Proposed next meeting or follow-up cadence

6. QUESTIONS TO ASK THEM
   - Open-ended questions that surface their priorities
   - Questions that help qualify the opportunity
   - Questions that build the relationship beyond the transaction
```

### Step 5: Compile and Deliver Briefing

```
1. Assemble the briefing document (see Output Format below)

2. Save to file:
   write_file("meetings/briefs/{date}-{meeting_title}-brief.md", briefing_content)

3. Deliver to owner:
   send_message(chat_id=owner_id, text=briefing_summary)
   — Send 15-30 minutes before the meeting
   — Include the top 3 most important things to know
   — Link to full brief if it is long
```

---

## During/After Meeting: Processing & Follow-Up

### Step 6: Ingest Meeting Notes

Accept meeting notes from any source:

```
From owner's voice memo or typed notes:
  — Accept directly from conversation

From transcript file:
  read_file("/path/to/transcript.txt")

From recording platform:
  browser_navigate("https://otter.ai/meeting/[id]")
  web_extract(url=recording_url)

Preprocessing:
  - Map speakers to actual attendee names
  - Split into logical segments by topic
  - Note timestamps if available
```

### Step 7: Extract Structured Intelligence

Parse notes into these categories:

**Decisions Made**
- Scan for: "we decided", "let's go with", "agreed", "approved", "final answer"
- Capture: what was decided, who approved, what alternatives were discussed

**Action Items**
- Scan for: "[name] will", "I'll handle", "can you", "next step is", "by [date]"
- For each: task, owner, deadline, priority, dependencies
- Flag unassigned items: "someone should" → resolve to a specific person or mark unassigned

**Promises Made**
- Scan for: "I guarantee", "you'll have it by", "we commit to"
- Flag prominently — broken promises damage trust

**Unresolved Issues**
- Questions asked but not answered
- Topics tabled: "let's revisit", "park this for now"
- Disagreements not resolved

**Key Insights**
- New information learned about the attendee/company
- Shifts in their priorities or concerns
- Buying signals or risk signals (for sales meetings)
- Relationship dynamics observed

**Sentiment Assessment**
- Overall meeting tone: positive, neutral, tense, productive
- Specific tensions or enthusiasms noted
- Areas where alignment was strong or weak

### Step 8: Compare with Prior Meetings

```
1. Load prior meeting notes with same attendees:
   search_files(query="{attendee_name} meeting summary")
   read_file(matching_files)

2. Check for recurring unresolved issues:
   — Same issue raised 2+ times = flag as "Recurring Unresolved"
   — Calculate how many meetings this has been open

3. Track action item completion:
   — Were prior action items completed, in progress, or dropped?
   — Flag dropped items that were never discussed

4. Detect discussion loops:
   — Same topic 3+ meetings without resolution = flag
   — Recommend a dedicated working session
```

### Step 9: Draft Follow-Up Email

```
1. Generate follow-up email tailored to the meeting type:

   SALES MEETING → Warm, action-oriented, reinforce value proposition
   CUSTOMER CHECK-IN → Helpful, address concerns raised, confirm next steps
   INVESTOR MEETING → Professional, metrics-focused, clear asks
   INTERNAL SYNC → Brief, action-item focused, skip pleasantries
   PARTNERSHIP → Collaborative tone, mutual value emphasis

2. Structure:
   - Thank them for their time (1 sentence)
   - Summarize key decisions (bullet list)
   - List action items with owners and deadlines
   - Note any open items that need follow-up
   - Propose next meeting if appropriate
   - Close with clear next step

3. Personalize per recipient:
   — External attendees: only include what is relevant to them, omit internal items
   — Internal team: include full detail, flag items needing attention

4. Queue for review or auto-send:
   send_message(chat_id=owner_id, text="Follow-up email drafted for {meeting}. Review?")
```

### Step 10: File and Track

```
1. Save meeting summary:
   write_file("meetings/{topic}/{date}-{title}-summary.md", summary)

2. Update CRM if applicable:
   prospect_tool(action="update", id=prospect_id, notes=meeting_summary)

3. Create action item reminders:
   For each action item with a deadline, set a reminder

4. Update attendee intelligence profiles:
   — Add new information learned during the meeting
   — Update relationship status, sentiment, next steps

5. Send internal summary if needed:
   send_message(channel=team_channel, text=internal_summary)
```

---

## Output Format

### Pre-Meeting Briefing

```
MEETING BRIEF — {meeting_title}
{date} {time} ({duration}) | {location_or_link}
================================================

ATTENDEES:
  - {Name} ({Title}, {Company})
    Background: {career_summary}
    Recent news: {relevant_recent_activity}
    CRM: {tier}, {deal_stage}, last contact {date}
    Rapport builder: {shared_interest_or_connection}

  - {Name} ({Title}, {Company})
    Background: {career_summary}
    Recent news: {relevant_recent_activity}

RELATIONSHIP HISTORY:
  - Last meeting: {date} — {key_outcome}
  - Open threads: {active_email_threads_or_discussions}
  - Our commitments to them: {list_with_status}
  - Their commitments to us: {list_with_status}

SUGGESTED TALKING POINTS:
  1. {Opener — rapport builder}
  2. {Key topic 1 — with prepared data point}
  3. {Key topic 2 — with question to ask}
  4. {Ask — what you want from this meeting}

WATCH OUT FOR:
  - {Overdue commitment on our side}
  - {Sensitive topic to handle carefully}
  - {Competitor mentioned in prior interaction}

GOAL FOR THIS MEETING:
  Primary: {desired outcome}
  Fallback: {minimum acceptable outcome}
```

### Post-Meeting Summary

```
MEETING SUMMARY — {title}
{date} | {duration} | Attendees: {names}
==========================================

DECISIONS:
  1. {Decision} — approved by {name}
  2. {Decision} — approved by {name}

ACTION ITEMS:
  | # | Task            | Owner   | Deadline | Priority |
  |---|-----------------|---------|----------|----------|
  | 1 | {task}          | {name}  | {date}   | High     |
  | 2 | {task}          | {name}  | {date}   | Medium   |

PROMISES MADE:
  - {Name} committed to {outcome} by {date}

UNRESOLVED:
  - {Issue} — raised by {name}, needs follow-up
  - {Issue} — tabled, revisit at next meeting

KEY INSIGHTS:
  - {New information learned}
  - {Shift in their priorities}

SENTIMENT: {positive/neutral/tense} — {brief explanation}

RECURRING ISSUES (from prior meetings):
  - {Issue} — open for {N} meetings, first raised {date}

NEXT MEETING: {date/time if scheduled}
```

### Follow-Up Email Draft

```
TO: {attendee_emails}
SUBJECT: Follow-up: {meeting_title} — {date}

Hi {Name},

Thanks for taking the time today. Here is a quick recap:

Key Decisions:
- {Decision 1}
- {Decision 2}

Action Items:
- [ ] {Task} — {owner} — by {date}
- [ ] {Task} — {owner} — by {date}

Open Items:
- {Item needing follow-up}

{Proposed next step or next meeting}

Let me know if I missed anything.

Best,
{Owner name}
```

---

## Examples

### Example 1: Pre-Meeting Research

**Input:** "I have a call with Jane Park from Clearbit tomorrow at 2pm. Prep me."

**Process:**
1. Pull calendar event → Attendee: jane.park@clearbit.com, Topic: "Partnership Discussion"
2. Research Jane Park: VP of Partnerships at Clearbit, 3 years in role, previously at Segment
3. Research Clearbit: B2B data enrichment, recently acquired by HubSpot, 200 employees
4. Check CRM: No prior relationship. Cold intro from mutual connection (Mark).
5. Check email: One email thread with Mark's intro, Jane expressed interest in data partnerships
6. Generate briefing with talking points focused on mutual data value, integration opportunities

**Output:** Full briefing doc delivered 30 minutes before the call via Telegram.

### Example 2: Post-Meeting Processing

**Input:** User pastes meeting notes after a client call with Acme Corp.

**Process:**
1. Parse notes, identify 2 decisions, 5 action items, 1 unresolved issue
2. Cross-reference with prior Acme meetings: 1 recurring unresolved issue (API migration timeline — raised 3 times)
3. Draft follow-up email personalized for client (external-safe) and internal summary
4. Update CRM with meeting notes and deal stage progression
5. Set reminders for the 3 action items with deadlines

**Output:** Follow-up email queued for review, internal summary posted, CRM updated, reminders set.

### Example 3: Pre-Meeting with Investor

**Input:** (Auto-trigger) Meeting with investor Sarah Tavel in 15 minutes.

**Process:**
1. Research Sarah Tavel: GP at Benchmark, board member at several companies, writes about marketplace dynamics
2. Check CRM: Warm relationship, met at conference 2 months ago, follow-up call agreed
3. Check recent activity: Published blog post about AI-native businesses last week
4. Prepare talking points: reference her blog post, show metrics she cares about (NRR, CAC payback)

**Output:** Quick brief via Telegram: "Meeting with Sarah Tavel (Benchmark) in 15 min. She just wrote about AI-native businesses — good opener. Key metrics to share: NRR at 135%, CAC payback 8 months. Full brief attached."

---

## Error Handling

- **Attendee not found online**: State what was found and what was not. Ask owner for more context (LinkedIn URL, company name).
- **No prior relationship data**: Clearly state "No prior interactions found in CRM or email." Recommend the owner share context about how they know this person.
- **Calendar event missing attendee emails**: Ask the owner for attendee contact info before attempting research.
- **Meeting notes are incomplete or unclear**: Flag uncertain sections with [unclear] and ask the owner to fill gaps before sending follow-up.
- **Conflicting information**: If web research conflicts with CRM data (e.g., person changed companies), flag the discrepancy and ask the owner to confirm.
- **Time pressure**: If the meeting is in less than 5 minutes, send a quick 3-line brief instead of the full document. Deliver the full brief after the meeting for reference.
