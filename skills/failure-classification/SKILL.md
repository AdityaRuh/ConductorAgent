---
name: failure-classification
description: Classify agent failures and determine recovery action
---

# Failure Classification

When an agent reports failure, classify it before deciding recovery.

## Classification Rules

### Transient Failures
**Signals:** HTTP 429, 502, 503, ECONNRESET, ETIMEDOUT, "rate limit", "temporarily unavailable"
**Action:** Retry with exponential backoff (30s → 60s → 120s). Max 3 retries.
**Budget cost:** Minimal — charge only the failed attempt tokens.

### Logical Failures
**Signals:** Malformed output, wrong classification, empty plan, tests don't compile, agent returned but output is invalid
**Action:** Re-run agent with explicit format constraints appended to context. Max 2 retries.
**Budget cost:** Full retry cost charged.

### Dependency Failures
**Signals:** Upstream stage not complete, missing Pathfinder comment, PR not found, branch doesn't exist, Linear ticket in wrong state
**Action:** Do NOT retry. Set task to BLOCKED with reason. Re-check on next heartbeat — dependency may resolve naturally.
**Budget cost:** None (no agent invoked).

### Budget Failures
**Signals:** Task `budget.spent >= budget.allocated`, agent reports token limit
**Action:** Immediately BLOCK task. Escalate to human with full budget breakdown.
**Budget cost:** N/A — budget is the problem.

### Health Failures
**Signals:** Agent container not running, webhook server unreachable, gateway disconnected, agent hasn't run in 3+ expected cycles
**Action:** Attempt restart (once). If restart fails, escalate immediately.
**Budget cost:** None.

### Unknown Failures
**Signals:** Anything not matching above categories. Unrecognized error messages, unexpected state transitions, agent hung without response.
**Action:** Do NOT retry. Escalate immediately with full context dump (task state, agent logs, last known output).

## Escalation Message Format

```
🎛️ Conductor — Failure Escalation

Ticket: {ticketId} — {title}
Agent: {agentName}
Stage: {currentStage}
Failure Type: {classification}
Error: {error message or summary}
Attempts: {current}/{max}
Budget: {spent}/{allocated} tokens

Suggested Action: {what the human should do}
```

## Never

- Retry an unknown failure
- Retry after budget exhaustion
- Retry more than 3 times for transient, 2 times for logical
- Retry a dependency failure (wait instead)
- Classify without reading the actual error
