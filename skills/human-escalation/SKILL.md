---
name: human-escalation
description: Determine when and how to escalate to human operators
---

# Human Escalation

Escalation is not failure — it is the correct response when autonomous resolution is insufficient or risky.

## Escalation Triggers

### Mandatory Escalation (always escalate)
- Unknown failure type
- Budget exhausted for a task
- Agent unhealthy for 3+ consecutive cycles
- PR review loop hit 5 iterations without approval
- CI failed 3 consecutive times after fix attempts in a single loop iteration
- Reviewer left explicitly subjective/design-level feedback (flagged by PR Resolver's intent classifier as `SUBJECTIVE`)
- Security-sensitive file modified (credentials, env files, auth middleware)

### Warning (notify, don't block)
- Budget at 80% consumed
- Agent degraded (1-2 missed cycles)
- PR review loop at iteration 3+ (getting close to limit)
- Task stuck in same stage for 2+ hours

### No Escalation Needed
- Transient failure with retries remaining
- Dependency failure (will self-resolve)
- Normal stage advancement
- Successful completion

## Escalation Channels

| Priority | Channel | Format |
|----------|---------|--------|
| Critical (agent down, unknown failure) | Telegram + mention | Detailed with logs |
| High (budget, loop limit) | Telegram | Structured summary |
| Warning (approaching limits) | Telegram (silent) | Brief one-liner |

## Response Handling

When a human responds to an escalation:
1. Read the response from Telegram
2. Match to the pending escalation by ticket ID
3. Apply the instruction:
   - "retry" → reset task status to PENDING, clear failure count
   - "skip" → advance to next stage, mark current as SKIPPED
   - "cancel" → mark task CANCELLED
   - "increase budget" → update budget.allocated, resume
   - "ignore" → keep BLOCKED, do not re-escalate for this issue
   - Custom instruction → store in task state as `humanOverride`, apply on next cycle

## De-escalation

A BLOCKED task automatically unblocks when:
- Human explicitly responds with an action
- The underlying condition resolves (e.g., agent becomes healthy again)
- A ticket state change in Linear indicates human intervention

Never auto-unblock a budget escalation — human must explicitly increase or cancel.
