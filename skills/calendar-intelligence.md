# Calendar Intelligence

## When to Use

Activate this skill when:
- User says "schedule a meeting", "find time for", "when am I free"
- User says "prep me for my next meeting", "who am I meeting with"
- User says "protect my focus time", "block deep work time"
- User says "send meeting follow-up", "summarize that meeting"
- Before any meeting starts (auto-trigger 15 min prior)
- Daily morning briefing includes calendar review
- Conflict detected between new request and existing calendar

## What You Need

### Tools
- `calendar_read` — Fetch events from Google Calendar / Outlook
- `calendar_create` — Create events, send invites
- `calendar_update` — Modify existing events (reschedule, add notes)
- `calendar_delete` — Cancel events, send cancellation notices
- `email_read` — Pull relevant threads for meeting prep
- `email_send` — Send meeting briefs, follow-ups, reschedule notices
- `web_search` — Research attendees, companies, topics
- `prospect_tool` — Pull CRM data on meeting attendees
- `send_message` — Telegram notifications for upcoming meetings, conflicts
- `state_db` — Store energy patterns, meeting preferences, follow-up tasks
- `browser_navigate` — Check LinkedIn profiles, company pages for attendee research

### Data Needed
- Full calendar access (read/write)
- Owner's energy pattern preferences (when they do best deep work vs meetings)
- Meeting type preferences (duration defaults, buffer requirements)
- Attendee relationship data from CRM
- Recent email threads with attendees

## Process

### Capability 1: Smart Scheduling

When someone requests a meeting:

```
1. Parse the request:
   - Who: attendee names/emails
   - What: meeting purpose/agenda
   - Duration: explicit or infer from type (30min default, 60min for deep topics)
   - Urgency: how soon it needs to happen
   - Constraints: timezone, location, specific days

2. Check owner's calendar for availability:
   calendar_read(start=today, end=today+14d)

3. Apply scheduling rules:
   a. NEVER schedule during focus blocks (marked as "Deep Work" or "Focus")
   b. NEVER double-book without explicit approval
   c. Prefer to cluster meetings together (meeting days vs focus days)
   d. Add 15-min buffer between back-to-back meetings
   e. No meetings before 9am or after 6pm owner's timezone
   f. Prefer mornings for external calls, afternoons for internal

4. Check attendee availability if possible:
   - If Google Workspace: check free/busy
   - If external: propose 3 time slots

5. Propose options to owner or send directly:
   - If owner said "schedule it": pick best slot and send invite
   - If owner said "find time": propose 3 options with reasoning
```

**Scheduling intelligence — energy-aware patterns:**

```
ENERGY MAP (customize per owner):
  6am-9am:   Startup mode. Good for solo prep, email, planning.
  9am-12pm:  Peak energy. Protect for deep work or high-stakes meetings.
  12pm-1pm:  Lunch. No meetings unless absolutely necessary.
  1pm-3pm:   Good for collaborative meetings, brainstorms.
  3pm-5pm:   Winding down. Good for 1:1s, casual syncs.
  5pm-6pm:   Wrap-up. Quick standups only.
  After 6pm: Emergency only.

MEETING DAY STRATEGY:
  If >3 meetings already on a day → suggest a different day
  If day is currently meeting-free → protect it (suggest alternative)
  Cluster meetings on Tue/Thu, protect Mon/Wed/Fri for focus (adjustable)
```

### Capability 2: Conflict Detection & Resolution

Run automatically when new events are created or modified.

```
1. Scan upcoming 7 days for conflicts:
   calendar_read(start=today, end=today+7d)

2. Detect conflict types:
   a. HARD CONFLICT — Two events overlap on the same calendar
   b. SOFT CONFLICT — Event during focus block or lunch
   c. TRAVEL CONFLICT — Back-to-back events in different locations with no travel time
   d. ENERGY CONFLICT — 4+ meetings in a row with no break
   e. PREP CONFLICT — Important meeting with no prep time allocated

3. For each conflict, propose resolution:
   - Reschedule the lower-priority event
   - Shorten one event to create buffer
   - Delegate attendance to team member
   - Convert to async (send questions via email instead)

4. Notify owner:
   send_message(chat_id=owner_id, text="Calendar conflict detected for Thursday:
   [Meeting A] overlaps [Meeting B] at 2pm. Recommend rescheduling B to 3:30pm. Approve?")
```

### Capability 3: Meeting Prep Briefs

Auto-trigger 15 minutes before any meeting, or on-demand when asked.

```
1. Get upcoming meeting details:
   calendar_read(event_id=next_meeting)
   → Extract: title, attendees, agenda, description, previous notes

2. Research each attendee:
   For each attendee:
     a. Check CRM:
        prospect_tool(action="search", query=attendee_email)
        → Role, company, deal stage, last interaction, notes

     b. Check email history:
        email_read(search=f"from:{attendee_email} OR to:{attendee_email}", limit=10)
        → Recent conversations, open threads, promises made

     c. Check web (for external attendees):
        web_search(query=f"{attendee_name} {attendee_company} recent news")
        → Recent press, funding, product launches, LinkedIn updates

     d. Check LinkedIn (for important meetings):
        browser_navigate(url=f"linkedin.com/in/{attendee_linkedin}")
        → Current role, recent posts, mutual connections

3. Pull relevant documents:
   - Search email for attachments related to meeting topic
   - Check shared drives for related proposals, decks, contracts

4. Compile meeting brief and deliver:
   send_message(chat_id=owner_id, text=brief) OR email_send(to=owner, subject=f"Brief: {meeting_title}")
```

### Capability 4: Post-Meeting Follow-Up

Trigger after a meeting ends (calendar event end time) or when user says "send follow-up."

```
1. Prompt owner for meeting notes (or accept voice memo):
   send_message(chat_id=owner_id, text="Your meeting with {attendees} just ended. Key takeaways?
   Reply with notes or say 'skip' if no follow-up needed.")

2. If notes provided, generate follow-up:
   a. Summarize decisions made
   b. List action items with owners and deadlines
   c. Note any open questions or parking lot items
   d. Propose next meeting date if recurring topic

3. Draft follow-up email:
   - To: all attendees
   - Subject: "Follow-up: {meeting_title} — {date}"
   - Body: summary, action items, next steps

4. Send or queue for review:
   If auto-send enabled: email_send(to=attendees, subject=..., body=...)
   If review needed: Queue and notify owner

5. Create follow-up tasks:
   For each action item:
     state_db(action="create_task", title=item, owner=assignee, due=deadline)
```

### Capability 5: Focus Time Protection

Runs as a background rule, always active.

```
1. At the start of each week, analyze the calendar:
   calendar_read(start=monday, end=friday)

2. Calculate focus time available:
   total_hours = sum(non_meeting_blocks > 90min)

3. If focus time < threshold (e.g., < 8 hours/week):
   a. Identify movable meetings (recurring, low-priority, internal)
   b. Propose rescheduling to create focus blocks
   c. Auto-decline new meeting requests during focus blocks (with polite message)

4. Protect existing focus blocks:
   When new meeting request arrives during focus block:
   → Auto-respond: "I have a focus block at that time. Here are alternatives: [3 slots]"
   → Notify owner: "Declined meeting from {requester} during your focus block. Proposed alternatives."

5. Weekly report:
   "This week: 12 hours of focus time protected. 3 meeting requests redirected."
```

## Output Format

### Meeting Prep Brief

```
MEETING BRIEF — {meeting_title}
{date} {time} ({duration}) | {location/link}
========================================

ATTENDEES:
  - Sarah Chen (VP Engineering, Acme Corp)
    CRM: Tier 1 customer, $120K ARR, deal expanding
    Last contact: 3 days ago (email about API v2.3 issue)
    Recent news: Acme raised Series C ($45M) last week

  - James Liu (CTO, Acme Corp)
    CRM: Technical decision maker
    Last contact: 2 weeks ago (product demo)
    LinkedIn: Posted about scaling microservices yesterday

CONTEXT:
  - Open thread: API v2.3 integration issue (Sarah emailed 3 days ago)
  - Their contract renews in 45 days
  - They've been evaluating a competitor (mentioned in last call)

SUGGESTED TALKING POINTS:
  1. Address the v2.3 issue — show fix timeline
  2. Discuss expansion: they need 3 more seats
  3. Mention new features relevant to their microservices stack
  4. Soft close on renewal before competitor evaluation goes further

OPEN COMMITMENTS TO THEM:
  - Promised API fix by end of week (you, 2 days remaining)
  - Promised custom report template (engineering, overdue by 3 days)
```

### Follow-Up Email Draft

```
TO: sarah.chen@acme.com, james.liu@acme.com
SUBJECT: Follow-up: API Integration Sync — March 30

Hi Sarah and James,

Great chatting today. Here's a summary:

DECISIONS:
  - Moving forward with v2.4 migration path (skip v2.3 fix)
  - Acme team will start testing in staging next Monday

ACTION ITEMS:
  - [ ] {Owner}: Send v2.4 migration guide by Thursday
  - [ ] Sarah: Share staging environment credentials
  - [ ] James: Confirm team capacity for testing sprint

NEXT MEETING: Thursday April 3 at 2pm PT (invite sent)

Let me know if I missed anything.

Best,
{Owner name}
```

### Weekly Calendar Health Report

```
CALENDAR HEALTH — Week of March 30
====================================
Total meetings: 18 (up from 14 last week)
Focus blocks: 6 hours (down from 10 — below 8hr threshold)
Back-to-back chains: 3 (longest: 4 meetings, no break)
Conflicts resolved: 2

RECOMMENDATIONS:
  1. Move Thursday standup to async — saves 30min
  2. Combine Friday 1:1s into group sync — saves 45min
  3. Add focus block Wednesday AM — currently unprotected

NEXT WEEK FORECAST:
  Monday: Light (2 meetings) — good focus day
  Tuesday: Heavy (5 meetings) — cluster day
  Wednesday: Open — protect for deep work
  Thursday: Medium (3 meetings) — all afternoon
  Friday: Light (1 meeting) — wrap-up day
```

## Examples

### Example 1: Schedule a Meeting

**Input:** "Schedule a call with Sarah Chen from Acme this week to discuss the API issue"

**Process:**
1. Look up Sarah Chen in CRM → found, Tier 1, recent API complaint
2. Check calendar this week → Tuesday 2-3pm and Thursday 10-11am are good slots
3. Tuesday clusters with existing meetings (preferred), Thursday is a focus day (avoid)
4. Duration: 30 min (issue discussion, not strategic)

**Output:**
```
I'll schedule with Sarah Chen (Acme, Tier 1).
Best slot: Tuesday 2:00-2:30pm — clusters with your other meetings.
Sending invite now with agenda: "API v2.3 Integration — Resolution Discussion"
Prep brief will arrive 15 min before.
```

### Example 2: Morning Calendar Review

**Input:** "What's on my calendar today?"

**Process:**
1. Pull today's events
2. Check for conflicts, prep needs, energy issues
3. Research attendees for external meetings
4. Generate briefs for important meetings

**Output:**
```
TODAY — March 30
  9:00am  Focus block (protected)
  10:30am Team standup (15 min, internal)
  11:00am Call with James Wu — NEW LEAD, demo request
          → Brief ready. He's CTO at a Series A startup, 50 employees.
  12:00pm Lunch
  2:00pm  Sarah Chen (Acme) — API discussion
          → Brief ready. Key: address v2.3 before renewal in 45 days.
  4:00pm  1:1 with marketing lead

Focus time available: 3.5 hours (morning block + after 4:30pm)
No conflicts detected.
```

### Example 3: Protect Focus Time

**Input:** (Automatic) New meeting invite during Wednesday focus block

**Process:**
1. Detect: invite from internal team member for "quick sync"
2. Check: Wednesday AM is marked as focus block
3. Find alternatives: Wednesday 3pm, Thursday 10am, Friday 2pm

**Output to requester:**
```
Thanks for the invite! I have a focus block Wednesday morning.
Would any of these work instead?
  - Wednesday 3:00pm
  - Thursday 10:00am
  - Friday 2:00pm
```

**Output to owner (Telegram):**
```
Redirected meeting request from {person} away from your
Wednesday focus block. Proposed 3 alternatives.
```
