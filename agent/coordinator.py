# agent/coordinator.py
"""
Coordinator mode: smart delegation orchestration.

When an agent delegates a task, it should decide:
- CONTINUE an existing specialist (high context overlap)
- SPAWN FRESH (low overlap, or verifying another's work)

This module provides the system prompt additions and utility functions
for coordinator-mode delegation.

Ported from CC's coordinator/coordinatorMode.ts.
"""

COORDINATOR_SYSTEM_PROMPT = """
## Delegation Strategy

When delegating tasks to subagents, use this decision framework:

**Continue an existing specialist when:**
- The specialist just researched exactly the files/data needed for the next step
- You are correcting a failure and the specialist has the error context
- The next task is a direct continuation of what the specialist just did

**Spawn a fresh agent when:**
- You need to verify code/work that another specialist just produced (fresh eyes)
- The previous approach was entirely wrong (clean slate avoids anchoring)
- The new task is unrelated to what the specialist worked on
- The specialist's context would pollute the next task with irrelevant history

**Decomposing large tasks:**
1. Identify independent sub-tasks (those with no shared mutable state)
2. Delegate independent tasks in parallel via delegate_task_async
3. Delegate sequential tasks in order, passing results forward
4. Synthesize results yourself — don't delegate synthesis

**Naming specialists:**
- Use delegate_task(agent_name="researcher") for reusable research agents
- Use delegate_task(agent_name="writer") for drafting/editing agents
- Use message_agent("researcher", "also check X") for follow-up instructions
- Omit agent_name for one-off tasks

**Task decomposition template:**
When breaking a large task into parallel work:
1. List all independent sub-tasks
2. Start them all with delegate_task_async
3. Use check_delegation to collect results
4. Synthesize into final output
"""

COORDINATOR_TOOL_GUIDANCE = """
**Parallel delegation example:**
```
# Start parallel research
handle1 = delegate_task_async(goal="Research company A's funding history")
handle2 = delegate_task_async(goal="Research company B's funding history")
# Continue working while they run...
# Collect results
result1 = check_delegation(handle1, wait_seconds=60)
result2 = check_delegation(handle2, wait_seconds=60)
```

**Named specialist example:**
```
# First use - creates the specialist
delegate_task(agent_name="researcher", goal="Research Acme Corp")
# Follow-up - reuses same specialist with history
message_agent("researcher", "Now check their LinkedIn company page too")
```
"""


def get_coordinator_prompt_addition() -> str:
    """Return the coordinator guidance to inject into system prompts."""
    return COORDINATOR_SYSTEM_PROMPT + "\n" + COORDINATOR_TOOL_GUIDANCE
