# Tool-Use Planner

## Purpose

When given a complex task, decompose it into sub-tasks and map each to the most appropriate available tools. Create a clear execution plan showing every step, its tool, expected inputs and outputs, and dependencies between steps. Handle tool failures with fallback strategies. Present the plan to the owner for approval before executing.

## When to Use

Activate this skill when:
- User gives a task that requires 3 or more tool calls to complete
- User says "plan how to do [X]", "what's the approach for [X]", "how would you handle [X]"
- A task involves multiple tools that must be coordinated in a specific order
- A task has branching logic (if X then do Y, else do Z)
- A task involves external services that might fail (web searches, API calls, emails)
- User says "show me the plan before you do it", "don't just do it, walk me through it"
- Another skill triggers a multi-step workflow and needs orchestration
- A task is ambiguous and planning would help clarify the approach before executing

## What You Need

### Tools (meta — this skill uses ALL available tools)
This skill does not use tools directly. Instead, it plans which tools other steps should use. The available tool inventory includes:

```
COMMUNICATION:
  send_message    — Send messages via Telegram, email, Slack
  email_send      — Send emails via SMTP
  email_read      — Read emails via IMAP

FILE OPERATIONS:
  read_file       — Read a file from the filesystem
  write_file      — Write or create a file
  search_files    — Full-text search across files

WEB:
  web_search      — Search the internet for information
  web_extract     — Pull content from a specific URL
  browser_navigate — Navigate to a URL in a browser session
  browser_snapshot — Capture the current browser page state

DATA:
  state_db        — Read/write to the persistent state database
  prospect_tool   — CRM operations (add, update, search, list)
  calendar_read   — Read calendar events
  calendar_create — Create calendar events
  calendar_update — Modify calendar events

EXECUTION:
  terminal        — Run shell commands
  cron_create     — Schedule recurring tasks

MEDIA:
  image_generate  — Generate images from text prompts
  heygen_generate_video_tool — Generate AI video content

SOCIAL:
  (Platform-specific posting tools — see social-media-posting.md)
```

### Data Needed
- The user's task description (clear or ambiguous)
- Available tool inventory and their capabilities
- Context from prior conversations or files that informs the approach
- Owner's preferences for approval thresholds (auto-execute vs. review)

---

## Process

### Step 1: Parse the Task

Break down the user's request into atomic components:

```
TASK DECOMPOSITION:

1. Identify the GOAL:
   — What is the end state the user wants?
   — What does "done" look like?
   — Is there a deliverable (email, file, report, action)?

2. Identify INPUTS:
   — What information is needed to start?
   — What is already known vs. needs to be gathered?
   — Are there any files, names, URLs, or data points mentioned?

3. Identify CONSTRAINTS:
   — Deadlines or time pressure
   — Recipient-specific requirements
   — Quality standards (does this go external?)
   — Budget or resource limits
   — Owner preferences (auto-execute vs. review)

4. Identify UNKNOWNS:
   — What information is missing?
   — What assumptions are being made?
   — Where might the task branch based on what we discover?

5. List SUB-TASKS:
   — Break the goal into the smallest meaningful units of work
   — Each sub-task should map to 1-2 tool calls
   — Order them by dependency (what must happen before what)
```

### Step 2: Map Sub-Tasks to Tools

For each sub-task, select the best tool and define inputs/outputs:

```
TOOL SELECTION RULES:

  Information gathering:
    — Known file path       → read_file
    — Unknown file location → search_files
    — Person/company info   → web_search + web_extract
    — CRM data              → prospect_tool(action="search")
    — Calendar data         → calendar_read
    — Email history         → email_read

  Content creation:
    — Text content          → LLM generates directly (no tool needed)
    — Images                → image_generate
    — Video                 → heygen_generate_video_tool
    — Files/documents       → write_file

  Communication:
    — Email                 → email_send OR send_message
    — Telegram notification → send_message
    — Social media post     → platform-specific posting tool

  Data persistence:
    — Save to file          → write_file
    — Update CRM            → prospect_tool(action="update")
    — Create calendar event → calendar_create
    — Store metadata        → state_db

  Verification:
    — Fact check            → web_search
    — File exists           → read_file (check for error)
    — Email sent            → check send_message response
    — Quality check         → invoke output-quality-critic skill
```

### Step 3: Build the Execution Plan

Assemble sub-tasks into an ordered plan with dependencies:

```
PLAN STRUCTURE:

  Step [N]: [Step name]
    Tool: [tool_name]
    Input: [what this step needs — from user, from prior step, or hardcoded]
    Expected output: [what this step produces]
    Depends on: [which prior steps must complete first]
    Fallback: [what to do if this step fails]
    Auto-execute: [yes/no — does this need owner approval?]

DEPENDENCY TYPES:
  — SEQUENTIAL: Step B needs output from Step A → must wait
  — PARALLEL: Steps B and C are independent → can run simultaneously
  — CONDITIONAL: Step D only runs if Step C produces result X
  — OPTIONAL: Step E improves quality but isn't strictly needed
```

### Step 4: Identify Failure Points and Fallbacks

For every step that could fail, define a fallback:

```
COMMON FAILURE MODES AND FALLBACKS:

  web_search returns no results:
    → Try alternate search terms (broader, synonym, different phrasing)
    → Try web_extract on a known URL (company website, LinkedIn)
    → Proceed without this data, note the gap to the owner

  web_extract fails (page blocked, paywall, 404):
    → Try web_search for cached version
    → Try browser_navigate for JavaScript-rendered pages
    → Skip and note the gap

  email_send fails:
    → Check email format
    → Try alternate email address from CRM
    → Queue for retry in 15 minutes
    → Notify owner if persistent failure

  read_file returns error (file not found):
    → Try search_files with the filename
    → Try alternate paths (common directory structures)
    → Ask the owner for the correct path

  prospect_tool returns no results:
    → Search by alternate identifiers (name instead of email, company instead of person)
    → Create a new CRM entry if this is a new contact

  calendar_create fails (conflict):
    → Check for conflicts with calendar_read
    → Propose alternative times
    → Ask the owner to resolve

  Any tool times out:
    → Retry once after 30 seconds
    → If second attempt fails, skip and notify owner
    → Continue with remaining steps that don't depend on the failed step

  Quality check (output-quality-critic) blocks the output:
    → Apply auto-fixes
    → Re-check after fixes
    → If still blocked, escalate to owner with the specific issue
```

### Step 5: Present the Plan

Show the plan to the owner in a clear format before executing:

```
PLAN PRESENTATION:

  1. State the goal: "Here's my plan to accomplish [task]."
  2. Show the steps in order with tool mappings
  3. Highlight decision points: "At step 3, if we find X, I'll do Y. Otherwise, Z."
  4. Highlight risks: "Step 5 depends on web search. If that fails, I'll [fallback]."
  5. Estimate time: "This should take approximately [X] minutes."
  6. Ask for approval: "Should I proceed? Any steps you want me to skip or change?"

APPROVAL LEVELS:
  — AUTO-EXECUTE: Simple, low-risk tasks (reading files, searching, generating drafts)
  — REVIEW BEFORE SEND: Anything going to an external recipient
  — FULL APPROVAL: Multi-step workflows, anything involving money, new contacts, or commitments
```

### Step 6: Execute the Plan

After approval, execute step by step:

```
EXECUTION PROTOCOL:

  1. Execute steps in dependency order
  2. Run parallel steps simultaneously when possible
  3. After each step, verify the output before moving on
  4. If a step fails:
     a. Execute the fallback
     b. If fallback succeeds, continue
     c. If fallback fails, pause and notify owner
     d. Ask: "Step [N] failed. Should I skip it, retry, or try a different approach?"
  5. At conditional branches, evaluate the condition and take the correct path
  6. Before sending any external communication, run the output-quality-critic skill
  7. Log each step's result for the execution summary
```

### Step 7: Report Execution Results

After completing (or partially completing) the plan:

```
EXECUTION REPORT:

  1. Summary: "Completed [X] of [Y] steps."
  2. Results per step: what happened, what was produced
  3. Any failures: what failed, what fallback was used, what was skipped
  4. Deliverables: files created, messages sent, records updated
  5. Open items: anything that still needs attention
```

---

## Output Format

### Execution Plan

```
EXECUTION PLAN — {task_summary}
=================================

GOAL: {what we're trying to accomplish}
ESTIMATED TIME: {X} minutes
STEPS: {count}
APPROVAL NEEDED: {yes/no — for what}

PLAN:

  Step 1: {step_name}
    Tool: {tool_name}({key_parameters})
    Input: {what this step needs}
    Output: {what this step produces}
    Depends on: —
    Risk: LOW
    Auto-execute: YES

  Step 2: {step_name}
    Tool: {tool_name}({key_parameters})
    Input: {from Step 1 output}
    Output: {what this step produces}
    Depends on: Step 1
    Risk: MEDIUM — {why}
    Fallback: {what to do if this fails}
    Auto-execute: YES

  Step 3: {step_name}  [CONDITIONAL]
    Condition: If Step 2 found {X}
    Tool: {tool_name}({key_parameters})
    Input: {from Step 2 output}
    Output: {what this step produces}
    Depends on: Step 2
    Risk: LOW
    Auto-execute: YES

  Step 3b: {alternate_step_name}  [CONDITIONAL — else]
    Condition: If Step 2 did NOT find {X}
    Tool: {tool_name}
    ...

  Step 4: {step_name}  [REVIEW REQUIRED]
    Tool: {tool_name}({key_parameters})
    Input: {from prior steps}
    Output: {external communication}
    Depends on: Step 3
    Risk: HIGH — going to external recipient
    Quality check: output-quality-critic before sending
    Auto-execute: NO — needs your approval

  ─── PARALLEL BLOCK ───
  Step 5a: {step_name}
    Tool: {tool_name}
    Depends on: Step 4
    (runs simultaneously with 5b)

  Step 5b: {step_name}
    Tool: {tool_name}
    Depends on: Step 4
    (runs simultaneously with 5a)
  ─── END PARALLEL ───

  Step 6: {step_name}
    Tool: {tool_name}
    Depends on: Steps 5a AND 5b
    Output: {final deliverable}

RISKS:
  - Step 2 may fail if {reason} → Fallback: {strategy}
  - Step 4 requires quality review → Will auto-fix if score < 8

Proceed? [Y/N / modify steps]
```

### Execution Report

```
EXECUTION REPORT — {task_summary}
===================================

STATUS: {COMPLETE / PARTIAL / FAILED}
STEPS COMPLETED: {X}/{Y}
TIME TAKEN: {X} minutes

RESULTS:

  Step 1: {step_name} — DONE
    Result: {what happened}
    Output: {what was produced}

  Step 2: {step_name} — DONE
    Result: {what happened}

  Step 3: {step_name} — SKIPPED (condition not met)

  Step 3b: {alternate_name} — DONE
    Result: {what happened}

  Step 4: {step_name} — DONE (approved by owner)
    Result: {email sent to X, quality score 9/10}

  Step 5a: {step_name} — FAILED → FALLBACK USED → DONE
    Initial failure: {what went wrong}
    Fallback: {what was done instead}
    Result: {outcome}

  Step 5b: {step_name} — DONE

  Step 6: {step_name} — DONE

DELIVERABLES:
  - {file_path} — {description}
  - Email sent to {recipient} — {subject}
  - CRM updated for {prospect}
  - Calendar event created: {event}

OPEN ITEMS:
  - {anything that still needs attention}
```

---

## Examples

### Example 1: Research and Outreach Task

**Input:** "Find out about the CTO at Notion and send them a personalized outreach email."

**Plan:**
```
Step 1: Search for Notion CTO
  Tool: web_search("Notion CTO 2026")
  Output: Name, title confirmation

Step 2: Deep research on CTO
  Tool: web_extract(linkedin_url), web_search("{name} recent talks articles")
  Output: Background, interests, recent activity
  Depends on: Step 1

Step 3: Check CRM for prior relationship
  Tool: prospect_tool(action="search", query="{name}")
  Output: Prior interactions (if any)
  Parallel with: Step 2

Step 4: Draft personalized outreach
  Tool: LLM generates email using Step 2 + 3 data
  Output: Email draft
  Depends on: Steps 2 and 3

Step 5: Quality check
  Tool: output-quality-critic skill
  Output: Scored and potentially auto-fixed email
  Depends on: Step 4

Step 6: Send email [REVIEW REQUIRED]
  Tool: send_message(to=cto_email, body=reviewed_draft)
  Depends on: Step 5 (must pass quality check)
  Auto-execute: NO

Step 7: Log to CRM
  Tool: prospect_tool(action="add", data=research+outreach_log)
  Depends on: Step 6
```

### Example 2: Multi-Channel Content Creation

**Input:** "Create a LinkedIn post and matching Twitter thread about our new feature launch."

**Plan:**
```
Step 1: Read feature details
  Tool: read_file("products/feature-launch-brief.md")
  Output: Feature description, value props, key stats

Step 2a: Draft LinkedIn post [PARALLEL]
  Tool: LLM generates (using social-media-management skill guidelines)
  Output: LinkedIn post draft

Step 2b: Draft Twitter thread [PARALLEL]
  Tool: LLM generates (using social-media-management skill guidelines)
  Output: 3-5 tweet thread draft

Step 3: Quality check both
  Tool: output-quality-critic skill
  Output: Scored drafts

Step 4: Present for approval [REVIEW REQUIRED]
  Output: Both drafts shown to owner
  Auto-execute: NO

Step 5a: Post to LinkedIn [PARALLEL, after approval]
Step 5b: Post to Twitter [PARALLEL, after approval]

Step 6: Log to content calendar
  Tool: write_file("content/calendar.md", updated_entry)
```

### Example 3: Plan with Conditional Branching

**Input:** "Check if our proposal to Acme was opened. If yes, follow up. If no, wait and remind me tomorrow."

**Plan:**
```
Step 1: Check email tracking
  Tool: email_read(search="to:acme proposal tracking")
  Output: Open/read status

Step 2a: [IF OPENED] Draft follow-up
  Condition: Proposal was opened
  Tool: LLM generates follow-up referencing they reviewed it
  Output: Follow-up email draft

Step 2b: [IF NOT OPENED] Schedule reminder
  Condition: Proposal was NOT opened
  Tool: cron_create(time=tomorrow_9am, action="remind owner about Acme proposal")
  Output: Reminder set

Step 3: [Only if 2a] Quality check and send
  Tool: output-quality-critic → send_message
  Depends on: Step 2a
  Auto-execute: NO
```

---

## Planning Principles

```
1. SMALLEST POSSIBLE STEPS
   Each step should do exactly one thing. If a step description contains "and",
   split it into two steps.

2. EXPLICIT DEPENDENCIES
   Never assume steps can run in any order. If Step B needs Step A's output,
   say so. If they're independent, mark them as parallel.

3. FAIL-SAFE BY DEFAULT
   Every step that touches an external service (web, email, API) needs a fallback.
   Internal steps (read_file, write_file, LLM generation) rarely fail but should
   still handle file-not-found and similar errors.

4. QUALITY GATES BEFORE EXTERNAL OUTPUT
   Any step that sends something to a human (email, social post, message) must
   pass through the output-quality-critic skill first.

5. SHOW YOUR WORK
   The plan should be readable by a non-technical owner. No jargon.
   "Search the web for info about their CTO" not "Execute web_search with params."

6. ASK BEFORE ACTING
   When in doubt about any step, ask. It's better to over-communicate the plan
   than to silently make the wrong choice.

7. IDEMPOTENT STEPS
   Design steps so they can be safely retried. If Step 3 is "send email",
   make sure re-running it won't send a duplicate.
```

## Error Handling

- **User's task is ambiguous**: Ask clarifying questions before planning. Present your interpretation and ask "Is this what you mean?"
- **No tool available for a sub-task**: State what is needed and that no tool currently supports it. Suggest alternatives or manual steps the owner can take.
- **Plan is too long (20+ steps)**: Group related steps into phases. Present a high-level plan first, then detail each phase when the owner approves.
- **Mid-execution failure**: Pause, report what completed and what failed. Ask the owner whether to continue with remaining steps, retry the failed step, or abort.
- **Owner modifies the plan**: Re-evaluate dependencies. A change in one step may cascade to downstream steps. Re-present the updated plan before continuing.
