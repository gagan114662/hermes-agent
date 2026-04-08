# SOP Execution

## When to Use

- User says "run the [X] process", "follow the onboarding steps", "execute the SOP for..."
- User defines a new repeatable workflow and wants it saved
- A recurring task needs to be done the same way every time
- User asks "what's the process for...?" and a matching SOP exists
- User says "create an SOP for...", "document this workflow"
- Hermes detects a task that matches a known SOP pattern (e.g., "onboard this new client" triggers client-onboarding SOP)

## What You Need

### Tools
- `file_read` — Load SOP definitions from skills/ directory
- `file_write` — Save new or updated SOPs
- `send_message` — Notify stakeholders at checkpoint steps
- `browser_navigate` — Execute steps that require platform interaction
- `web_search` — Look up information needed during SOP execution
- `cron_create` — Schedule recurring SOP executions or deadline reminders
- `prospect_add` — For SOPs involving CRM updates
- `sms_send` — For SOPs requiring SMS notifications

### Data
- SOP files stored in `skills/sops/` directory
- Owner preferences for notification channels
- Team directory for assigning SOP steps to people
- Completion history (which SOPs ran, when, outcomes)

## SOP File Format

Every SOP is a structured markdown file with required sections:

```markdown
# SOP: [Name]

## Metadata
- **ID**: sop-[slug]
- **Version**: 1.0
- **Owner**: [who maintains this SOP]
- **Frequency**: [one-time | daily | weekly | per-event]
- **Estimated Duration**: [time]
- **Last Updated**: [date]

## Trigger
[What causes this SOP to run — explicit request, event detection, schedule]

## Prerequisites
[What must be true before starting — access, data, approvals]

## Steps

### Step 1: [Action Name]
- **Action**: [What to do — be specific and tool-aware]
- **Tool**: [Which Hermes tool to use]
- **Input**: [What data this step needs]
- **Output**: [What this step produces]
- **Verify**: [How to confirm this step succeeded]
- **On Failure**: [What to do if this step fails]

### Step 2: [Action Name]
...

## Checkpoints
[After which steps to pause and report progress to user]

## Exception Handling
[What to do when things go off-script]

## Completion Criteria
[How to know the SOP is fully done]

## Output
[What artifact or report is produced at the end]
```

## Process

### Loading and Executing an SOP

1. **Match the request** to an existing SOP:
   - Search `skills/sops/` for matching files by name/keyword
   - If no exact match, search by tags and descriptions
   - If no SOP found, ask user: "I don't have an SOP for that. Want me to create one?"

2. **Load the SOP** via `file_read`:
   ```
   file_read("skills/sops/client-onboarding.md")
   ```

3. **Verify prerequisites** before starting:
   - Check each prerequisite condition
   - If any fail, report which ones and what's needed
   - Do NOT proceed until all prerequisites are met

4. **Execute step by step**:
   - Announce each step before executing: "Step 3/8: Setting up Stripe billing..."
   - Execute the step using the specified tool
   - Verify the step succeeded using the verify condition
   - Log the result (pass/fail, output, timestamp)
   - If step fails, follow the On Failure instructions

5. **Pause at checkpoints**:
   - At each checkpoint step, report progress to user
   - Include: steps completed, steps remaining, any issues encountered
   - Wait for user acknowledgment before continuing (unless SOP says auto-continue)

6. **Handle exceptions**:
   - If an unexpected situation arises, check the Exception Handling section
   - If no guidance, pause and ask the user
   - Never skip a step silently — always log why

7. **Complete and report**:
   - Verify all completion criteria are met
   - Generate the specified output artifact
   - Log the SOP execution for history

### Creating a New SOP

1. **Gather the workflow** from user:
   - Ask: "Walk me through the process step by step"
   - For each step, ask: "What tool or platform do you use for this?"
   - Ask: "What can go wrong at each step?"
   - Ask: "How do you know it's done?"

2. **Draft the SOP** using the template format above

3. **Review with user**:
   - Present the draft
   - Ask: "Does this capture the full process? Any steps missing?"
   - Iterate until approved

4. **Save the SOP**:
   ```
   file_write("skills/sops/[slug].md", content)
   ```

5. **Test-run the SOP** (optional):
   - Execute it once in dry-run mode
   - Note any steps that need clarification
   - Update the SOP with learnings

## Built-in SOP Templates

### Client Onboarding
```
Step 1: Collect client info (name, email, company, plan)
Step 2: Create CRM record → prospect_add
Step 3: Send welcome email → send_message (email)
Step 4: Set up billing → browser_navigate to Stripe
Step 5: Create project workspace → browser_navigate to Linear/Notion
Step 6: Schedule kickoff call → send_message with calendar link
Step 7: Send onboarding checklist → send_message (email)
Checkpoint: Confirm client received everything
Step 8: Follow up in 48h → cron_create reminder
```

### Content Publishing
```
Step 1: Load draft from file or conversation
Step 2: Run quality check → output-quality-critic skill
Step 3: Format for platform (blog, social, newsletter)
Step 4: Upload/publish → browser_navigate to CMS
Step 5: Share on social channels → browser_navigate to social platforms
Step 6: Send to email list → browser_navigate to email tool
Step 7: Log in content calendar
Checkpoint: Verify live URLs work
Step 8: Schedule engagement check in 24h → cron_create
```

### Lead Qualification
```
Step 1: Receive lead info (name, company, source)
Step 2: Research company → web_search
Step 3: Check company size, funding, industry fit
Step 4: Score lead (1-10) based on ICP criteria
Step 5: If score >= 7: add to CRM as qualified → prospect_add
Step 6: If score >= 7: draft outreach → crm-sales-copilot skill
Step 7: If score < 7: add to nurture list
Step 8: Log qualification decision with reasoning
```

### Product Update Shipping
```
Step 1: Confirm release notes are ready
Step 2: Verify deployment status → browser_navigate to deploy dashboard
Step 3: Draft changelog post
Step 4: Draft customer email announcement
Step 5: Run quality check on all content → output-quality-critic skill
Checkpoint: Get owner approval on content
Step 6: Publish changelog → browser_navigate to blog/docs
Step 7: Send email to customers → send_message (email)
Step 8: Post on social media → browser_navigate to social platforms
Step 9: Notify support team of changes → send_message (Slack)
Step 10: Schedule "any issues?" check in 4h → cron_create
```

### Support Escalation
```
Step 1: Capture issue details (customer, problem, severity, timeline)
Step 2: Search knowledge base → knowledge-retrieval skill
Step 3: If known issue: provide resolution steps
Step 4: If unknown: create support ticket → browser_navigate to support tool
Step 5: If severity >= HIGH: notify on-call → send_message (Slack + SMS)
Step 6: If severity >= CRITICAL: page engineering lead → sms_send
Step 7: Draft customer response acknowledging the issue
Step 8: Set follow-up reminder → cron_create (every 2h until resolved)
Checkpoint: Confirm customer received response
Step 9: Track to resolution, update customer at each stage
```

## Output Format

### SOP Execution Report
```
## SOP Execution: [Name]
**Run Date**: [timestamp]
**Status**: Completed / Partial / Failed

### Steps Completed
1. [Step name] — done at [time] — [output summary]
2. [Step name] — done at [time] — [output summary]
...

### Steps Skipped/Failed
- Step 4: [reason] — [what was done instead]

### Artifacts Produced
- [List of outputs: emails sent, tasks created, records updated]

### Issues Encountered
- [Any problems and how they were handled]

### Follow-ups Scheduled
- [Cron jobs or reminders set]
```

### SOP Progress Update (at checkpoints)
```
SOP: [Name] — Progress Update
Completed: 4/8 steps
Current: Step 5 - [description]
Issues: [none / list]
ETA: [remaining time estimate]
Shall I continue?
```

## Examples

### Example 1: Running an Existing SOP
**Input**: "Onboard Acme Corp as a new client — contact is jane@acme.com, they're on the Pro plan"
**Action**:
1. Load `skills/sops/client-onboarding.md`
2. Execute steps with: name=Acme Corp, email=jane@acme.com, plan=Pro
3. At each step, use the specified tool
4. Pause at checkpoint, report progress
5. **Output**: Full execution report with all artifacts created

### Example 2: Creating a New SOP
**Input**: "Create an SOP for how we handle refund requests"
**Action**:
1. Ask user to walk through the refund process
2. Document each step with tools, inputs, outputs, failure modes
3. Save to `skills/sops/refund-request.md`
4. **Output**: "SOP saved. Want me to do a test run?"

### Example 3: Scheduled SOP
**Input**: "Run the content publishing SOP every Monday at 9am for the weekly newsletter"
**Action**:
1. Load the content publishing SOP
2. Create a cron job: `cron_create("monday-newsletter", "0 9 * * 1", "sop:content-publishing")`
3. **Output**: "Scheduled. Every Monday at 9am I'll run the content publishing SOP. I'll pause at the approval checkpoint before publishing."

## Error Handling

- **Missing prerequisite**: List what's missing, ask user to provide it, do not proceed
- **Step failure**: Follow the On Failure instruction; if none, pause and ask user
- **Tool unavailable**: Try browser_navigate as fallback; if that fails too, log and skip with user notice
- **SOP outdated**: If a step references something that no longer exists (dead URL, renamed field), flag it and suggest an SOP update
- **User unresponsive at checkpoint**: Wait 1 hour, then send a reminder via `send_message`; after 24h, pause the SOP and notify
