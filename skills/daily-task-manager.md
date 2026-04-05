# Daily Task Manager

Single source of truth for all operational tasks. Always read the file before answering questions about current work. Always update it in the same turn when task state changes.

## Task File Location

```
~/.hermes/workspace/tasks/current.md
```

**Never use memory files or conversation history as the source of truth.** Only this file.

## File Structure

```markdown
## Today
- [ ] Task description [due: YYYY-MM-DD] [Claude: action taken]

## Next up after today
- [ ] Task description [due: YYYY-MM-DD]

## Rules
- [Standing instructions and operating constraints]

## Backlog with due date
- [ ] Task description [due: YYYY-MM-DD]

## Every weekday
- [ ] Recurring task

## Recurring reminders
- [ ] Reminder [every: Monday]
```

## Task Management Rules

**When adding a task:**
- Check for duplicates first (normalize text comparison)
- Place in the right section based on due date
- Use YYYY-MM-DD format for all dates
- Mark `Claude:` when the assistant owns the action

**When completing a task:**
- Change `[ ]` to `[x]` immediately
- Do not delete — keep completed items visible until end-of-day

**When deferring a task:**
- Move from "Today" to "Next up" with updated due date
- Note reason in brackets

**Prioritization order:**
1. Explicit priorities (marked `[P1]`)
2. Due today
3. Recurring operating tasks
4. Time-ordered meetings
5. Everything else

## Scan on Every Check-in

Before reporting on tasks:
1. Read the file with `read_file`
2. Check for overdue items (due date < today)
3. Surface items under "Today" first
4. Flag anything blocking other work

## Updating the File

Use `write_file` or `patch` to make changes. Never batch updates — apply them in the same turn the state changes.

## Example

If Gagan says "I finished the investor deck", immediately:
1. Read the file
2. Find "investor deck" entry
3. Mark `[x]`
4. Write the file back
5. Confirm: "Marked done."
