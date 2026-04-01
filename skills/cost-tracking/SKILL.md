---
name: cost-tracking
description: Track token usage, enforce budget limits, and optimize model selection
---

# Cost Tracking

Every LLM invocation across all agents costs tokens. Conductor tracks spend per task and per agent to enforce budgets and optimize costs.

## Budget Allocation

When a new task is created, allocate budget based on complexity:

| Complexity | Total Budget | Pathfinder | NightShift | Review Loop | PR Automation |
|-----------|-------------|-----------|-----------|------------|--------------|
| S | 50,000 | 5,000 | 25,000 | 15,000 | 5,000 |
| M | 100,000 | 10,000 | 50,000 | 30,000 | 10,000 |
| L | 200,000 | 15,000 | 100,000 | 65,000 | 20,000 |
| XL | 400,000 | 25,000 | 200,000 | 130,000 | 45,000 |

Complexity is determined by:
1. Ticket labels (if explicit S/M/L/XL label)
2. Pathfinder output (after analysis, `complexity` field)
3. Default: M

## Tracking Method

After each agent run, update `state/budget/{TICKET-ID}.json`:

```json
{
  "ticketId": "RP-400",
  "complexity": "M",
  "allocated": 100000,
  "spent": 42000,
  "breakdown": {
    "pathfinder": 8500,
    "nightshift": 28000,
    "pr-review-bot": 0,
    "pr-resolver": 5500,
    "pr-automation": 0
  },
  "history": [
    { "agent": "pathfinder", "tokens": 8500, "at": "2026-04-01T10:18:00Z" },
    { "agent": "nightshift", "tokens": 28000, "at": "2026-04-01T11:45:00Z" },
    { "agent": "pr-resolver", "tokens": 5500, "at": "2026-04-01T12:30:00Z" }
  ]
}
```

## Token Estimation

If exact token counts are not available from agent output:
- Pathfinder run: ~5,000-15,000 tokens (depends on RCA vs TRD)
- NightShift per repo: ~20,000-50,000 tokens (depends on complexity)
- PR Resolver per comment: ~2,000-5,000 tokens
- PR Review Bot per PR: ~3,000-8,000 tokens
- PR Automation: ~1,000-3,000 tokens

## Thresholds

| Threshold | Action |
|-----------|--------|
| 60% spent | Log milestone |
| 80% spent | Send Telegram warning |
| 90% spent | Restrict to essential operations only |
| 100% spent | BLOCK task, escalate |

## Model Selection Hints

For future optimization (agents manage their own model selection today):
- Simple classification tasks → Haiku (cheapest)
- Code generation / review → Sonnet (balanced)
- Complex multi-repo architecture decisions → Opus (most capable)
- CI diagnosis / error parsing → Sonnet (sufficient)
