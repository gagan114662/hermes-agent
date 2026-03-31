# Project/Task Manager Sync

## When to Use

- User says "create a task for...", "add this to Linear/Jira/Asana/Notion/Trello"
- User asks for a status update on tasks, projects, or sprints
- User wants to chase overdue items or summarize blockers
- User requests a daily/weekly standup summary
- A conversation produces action items that need tracking
- User says "sync my tasks", "what's overdue?", "prepare my weekly update"

## What You Need

### Tools
- `browser_navigate` — Primary integration method for all platforms
- `web_search` — Look up API documentation, find endpoints, resolve platform-specific questions
- `send_message` — Notify owners about overdue items or status changes
- `file_read` — Load saved credentials, project mappings, or SOP files
- `cron_create` — Schedule recurring syncs (daily standups, weekly summaries)

### Data
- Platform credentials (stored in owner's config or accessed via browser session)
- Project/workspace mappings (which Linear team = which business function)
- Team member directory (name to platform username mapping)
- Priority definitions (what counts as P0 vs P1 in this org)

## Supported Platforms

### Linear
- **Auth**: API key or browser session
- **API Base**: `https://api.linear.app/graphql`
- **Create Task**: GraphQL mutation `issueCreate` with title, description, teamId, assigneeId, priority, labelIds
- **Update Status**: mutation `issueUpdate` with stateId (Backlog, Todo, In Progress, Done, Cancelled)
- **Query Tasks**: query `issues` with filters (assignee, state, team, dueDate, priority)
- **Browser Fallback**: Navigate to `https://linear.app/[workspace]/team/[team]/active`, use DOM to read/create issues

### Jira
- **Auth**: API token + email, or browser session
- **API Base**: `https://[domain].atlassian.net/rest/api/3/`
- **Create Task**: POST `/issue` with fields: project.key, summary, description (ADF format), issuetype.name, assignee, priority
- **Update Status**: POST `/issue/[KEY]/transitions` with transitionId
- **Query Tasks**: GET `/search?jql=assignee=currentUser() AND status!=Done ORDER BY duedate`
- **Browser Fallback**: Navigate to board URL, read columns, click "Create" button

### Asana
- **Auth**: Personal access token or OAuth
- **API Base**: `https://app.asana.com/api/1.0/`
- **Create Task**: POST `/tasks` with name, notes, projects, assignee, due_on
- **Update Status**: PUT `/tasks/[gid]` with completed: true or custom_fields
- **Query Tasks**: GET `/tasks?project=[id]&completed_since=now&opt_fields=name,due_on,assignee,completed`
- **Browser Fallback**: Navigate to project URL, interact with task list

### Notion
- **Auth**: Integration token
- **API Base**: `https://api.notion.com/v1/`
- **Create Task**: POST `/pages` with parent database_id and properties (Title, Status, Assignee, Due Date)
- **Update Status**: PATCH `/pages/[id]` with properties.Status.select.name
- **Query Tasks**: POST `/databases/[id]/query` with filter on Status, Due Date, Assignee
- **Browser Fallback**: Navigate to database URL, use "New" button

### Trello
- **Auth**: API key + token
- **API Base**: `https://api.trello.com/1/`
- **Create Task**: POST `/cards` with name, desc, idList, idMembers, due
- **Update Status**: PUT `/cards/[id]` with idList (move between columns)
- **Query Tasks**: GET `/boards/[id]/cards?fields=name,due,idMembers,idList`
- **Browser Fallback**: Navigate to board URL, drag cards or use "Add a card"

## Process

### Creating a Task from Conversation

1. **Extract task details** from conversation context:
   - Title: concise, action-oriented ("Ship v2 pricing page", not "pricing")
   - Description: relevant context, links, acceptance criteria
   - Assignee: resolve name to platform user ID
   - Priority: infer from urgency words ("ASAP" = P0, "when you get a chance" = P3)
   - Due date: extract explicit dates or infer ("end of week" = Friday, "next sprint" = sprint end date)
   - Labels/tags: match to existing labels in the project

2. **Confirm with user** before creating:
   ```
   I'll create this task in Linear:
   - Title: Ship v2 pricing page
   - Assignee: @sarah
   - Priority: High
   - Due: Friday March 28
   - Team: Frontend
   Shall I go ahead?
   ```

3. **Create the task** via API (preferred) or browser automation:
   - Use `browser_navigate` to the platform
   - If API: construct the request, send it, parse the response for the task ID/URL
   - If browser: navigate to create form, fill fields, submit

4. **Confirm creation** — return the task URL and ID to user

5. **Log the mapping** — save conversation-to-task link for future reference

### Chasing Overdue Items

1. **Query all tasks** with due_date < today AND status != Done
2. **Group by assignee** and sort by days overdue
3. **For each overdue item**, compose a chase message:
   ```
   Hey [name], quick heads up — "[task title]" was due [X days ago].
   Can you update the status or give an ETA? Let me know if you're blocked.
   ```
4. **Send via preferred channel** using `send_message` (Slack, email, or SMS based on owner config)
5. **Log the chase** so we don't double-nag within 24 hours

### Daily Standup Summary

1. **Pull yesterday's completed tasks** (status changed to Done in last 24h)
2. **Pull today's in-progress tasks** (status = In Progress)
3. **Pull blockers** (tasks tagged "blocked" or with blocker comments)
4. **Pull overdue items** (due_date < today, not done)
5. **Format the summary**:
   ```
   ## Daily Update — March 25, 2026

   ### Done Yesterday
   - [FE-142] Pricing page responsive fixes (@sarah)
   - [BE-89] Stripe webhook retry logic (@dev)

   ### In Progress Today
   - [FE-145] Dashboard analytics widget (@sarah)
   - [BE-91] Rate limiting middleware (@dev)

   ### Blocked
   - [FE-143] SSO integration — waiting on Okta credentials (3 days)

   ### Overdue
   - [BE-87] Database migration script — due Mar 22 (@dev) — 3 days overdue
   ```

6. **Deliver** via `send_message` to configured channel (Slack #standup, email, etc.)

### Weekly Summary

1. Pull all tasks completed this week, tasks started, tasks carried over
2. Calculate velocity (points/tasks completed vs planned)
3. Identify recurring blockers (same items blocked for 2+ weeks)
4. List upcoming deadlines for next week
5. Format as executive summary with metrics:
   ```
   ## Week of March 24-28, 2026

   **Velocity**: 34 points completed (target: 40) — 85%
   **Completed**: 12 tasks | **Started**: 8 tasks | **Carried Over**: 5 tasks

   ### Highlights
   - Shipped pricing page v2 (3 days ahead of schedule)
   - Resolved Stripe webhook reliability issue

   ### Concerns
   - SSO integration blocked for 2nd consecutive week
   - Backend velocity declining (40 → 34 → 28 over 3 weeks)

   ### Next Week Focus
   - [P0] SSO go-live (unblock credentials first)
   - [P1] Dashboard analytics MVP
   - [P1] Load testing before launch
   ```

## Output Format

### Task Creation Response
```
Task created: [PLATFORM-ID] "[Title]"
URL: [direct link]
Assignee: [name] | Priority: [level] | Due: [date]
```

### Status Update Response
```
Updated [PLATFORM-ID] "[Title]": [Old Status] -> [New Status]
```

### Overdue Chase Response
```
Chased 3 overdue items:
- [FE-143] SSO integration (5 days overdue) — messaged @sarah via Slack
- [BE-87] DB migration (3 days overdue) — messaged @dev via Slack
- [MK-12] Blog post review (1 day overdue) — messaged @content via email
```

## Examples

### Example 1: Conversation to Task
**Input**: "Sarah needs to fix the mobile nav by Thursday"
**Action**:
1. Parse: title="Fix mobile navigation", assignee=sarah, due=Thursday, priority=medium (no urgency markers)
2. Confirm with user
3. `browser_navigate` to Linear, create issue in Frontend team
4. **Output**: `Task created: FE-156 "Fix mobile navigation" — assigned to @sarah, due Thu Mar 27`

### Example 2: Morning Standup Prep
**Input**: "Prepare my standup update"
**Action**:
1. Query Linear for my tasks updated in last 24h
2. Query for my current in-progress items
3. Check for any blockers on my items
4. **Output**: Formatted standup with Done/Doing/Blocked sections

### Example 3: Overdue Chase
**Input**: "Chase overdue tasks for the frontend team"
**Action**:
1. Query Linear: `team:Frontend AND dueDate < today AND state != Done`
2. Group by assignee, compose personalized messages
3. Send via Slack using `send_message`
4. **Output**: Summary of who was chased and what about

### Example 4: Cross-Platform Sync
**Input**: "Move all my Trello cards to Linear"
**Action**:
1. `browser_navigate` to Trello board, extract all cards with details
2. Map Trello lists to Linear states (To Do -> Todo, Doing -> In Progress, Done -> Done)
3. Create each task in Linear with preserved descriptions, due dates, labels
4. **Output**: Migration report with old/new ID mapping

## Error Handling

- **Auth expired**: Notify user, request re-authentication, retry
- **Rate limited**: Back off exponentially, batch remaining operations
- **Task not found**: Search by title fuzzy match, ask user to clarify
- **Platform down**: Fall back to browser automation, or queue the operation for retry via `cron_create`
- **Duplicate detection**: Before creating, search for existing tasks with similar titles within the same project
