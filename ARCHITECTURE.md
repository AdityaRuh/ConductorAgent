# ARCHITECTURE.md — Conductor Orchestrator

## System Overview

Conductor is a meta-agent that coordinates five specialized agents in a Linear-to-merged-code pipeline. It does not perform development work itself — it manages lifecycle, routing, health, budgets, and recovery.

---

## Pipeline Topology

```
                          ┌─────────────────────────────────────┐
                          │          CONDUCTOR (this agent)      │
                          │     Heartbeat: every 15 minutes      │
                          │                                      │
                          │  Reads: Linear API + state/tasks/    │
                          │  Decides: which agent runs next      │
                          │  Tracks: health, budget, metrics     │
                          │  Escalates: Telegram on failure      │
                          └──────┬──────┬──────┬──────┬──────┬──┘
                                 │      │      │      │      │
                    ┌────────────┘      │      │      │      └────────────┐
                    ▼                   ▼      │      ▼                   ▼
             ┌─────────────┐  ┌──────────────┐│┌─────────────┐  ┌────────────────┐
             │ PATHFINDER   │  │ NIGHTSHIFT   │││ PR RESOLVER │  │ PR AUTOMATION  │
             │ 30min cycle  │  │ 60min cycle  │││ 30min cycle │  │ on-demand      │
             │ Todo →       │  │ Ready4Dev →  │││ InDev →     │  │ Approved →     │
             │ InProgress   │  │ CodeReview   │││ CodeReview  │  │ Released       │
             └─────────────┘  └──────────────┘│└─────────────┘  └────────────────┘
                                              │
                                     ┌────────────────┐
                                     │ PR REVIEW BOT  │
                                     │ webhook-driven │
                                     │ posts reviews  │
                                     └────────────────┘
```

---

## Linear State Machine (Conductor's View)

```
  Todo
   │  ← Pathfinder watches
   ▼
  In Progress
   │  ← Pathfinder transitions here after posting plan
   │  ← Human/lead moves to Ready for Development when plan is approved
   ▼
  Ready for Development
   │  ← NightShift watches
   ▼
  In Development
   │  ← NightShift transitions here on start; PR Resolver watches
   ▼
  Code Review
   │  ← NightShift transitions here after PR created
   │  ← PR Resolver transitions here after comments resolved
   │
   │  PR Review Bot posts review comments (webhook)
   │  If changes requested → PR Resolver picks up (In Development)
   │  Loop until approved
   ▼
  Ready to Deploy - QA
   │  ← PR Automation cherry-picks into QA release branch
   ▼
  In QA
   │  ← QA testing
   ▼
  Approved for Prod
   │  ← PR Automation cherry-picks into Prod release branch
   ▼
  Released to Prod ✓
```

---

## Agent Registry

| # | Agent | Location | Trigger | Interval | Input State | Output State |
|---|-------|----------|---------|----------|-------------|--------------|
| 1 | Pathfinder | `agents/pathfinder-agent/` | Heartbeat | 30min | Todo | In Progress |
| 2 | NightShift | `agents/NightShift/` | Python poll | 60min | Ready for Development | In Development → Code Review |
| 3 | PR Review Bot | `agents/pr-review-bot/` | GitHub webhook | Event-driven | PR opened/updated | Posts review comments |
| 4 | PR Resolver | `agents/pr-resolver/` | Heartbeat | 30min | Require Changes | Code Review |
| 5 | PR Automation | `agents/pr-automation/` | Manual/CLI | On-demand | Ready to Deploy / Approved | In QA / Released |

---

## State Architecture

```
state/
├── tasks/
│   └── {TICKET-ID}.json        # Per-ticket lifecycle state
├── agents/
│   ├── pathfinder.json          # Agent health record
│   ├── nightshift.json
│   ├── pr-review-bot.json
│   ├── pr-resolver.json
│   └── pr-automation.json
├── metrics/
│   ├── daily.json               # Aggregated daily metrics
│   └── history/                 # Rolling 30-day history
└── budget/
    └── {TICKET-ID}.json         # Token usage per task
```

### Task State Schema (`state/tasks/{TICKET-ID}.json`)

```json
{
  "ticketId": "RP-400",
  "title": "Fix auth token refresh",
  "type": "bug",
  "priority": "high",
  "createdAt": "2026-04-01T10:00:00Z",
  "currentStage": "nightshift",
  "status": "RUNNING",
  "stages": {
    "pathfinder": {
      "status": "SUCCESS",
      "startedAt": "2026-04-01T10:15:00Z",
      "completedAt": "2026-04-01T10:18:00Z",
      "output": {
        "classification": "bug",
        "complexity": "M",
        "affectedRepos": ["sdr-backend"],
        "planCommentId": "comment_abc123"
      },
      "attempts": 1,
      "tokensUsed": 4200
    },
    "nightshift": {
      "status": "RUNNING",
      "startedAt": "2026-04-01T11:00:00Z",
      "completedAt": null,
      "output": null,
      "attempts": 1,
      "tokensUsed": 0
    },
    "pr-review-bot": { "status": "PENDING" },
    "pr-resolver": { "status": "PENDING" },
    "pr-automation": { "status": "PENDING" }
  },
  "reviewLoop": {
    "iteration": 0,
    "maxIterations": 5,
    "ciRepairAttempts": 0,
    "maxCiRepairs": 3
  },
  "budget": {
    "allocated": 100000,
    "spent": 4200,
    "currency": "tokens"
  },
  "pr": {
    "repo": null,
    "number": null,
    "branch": null,
    "url": null
  },
  "escalation": {
    "escalated": false,
    "reason": null,
    "escalatedAt": null,
    "resolvedAt": null
  },
  "updatedAt": "2026-04-01T11:00:00Z"
}
```

### Agent Health Schema (`state/agents/{agent}.json`)

```json
{
  "agentId": "pathfinder",
  "lastRunAt": "2026-04-01T10:15:00Z",
  "lastSuccessAt": "2026-04-01T10:15:00Z",
  "lastFailureAt": null,
  "consecutiveFailures": 0,
  "totalRuns": 47,
  "totalSuccesses": 45,
  "totalFailures": 2,
  "averageLatencyMs": 180000,
  "status": "healthy",
  "lastError": null
}
```

---

## Failure Classification Matrix

| Signal | Classification | Action |
|--------|---------------|--------|
| HTTP 429 / timeout / ECONNRESET | Transient | Retry with exponential backoff (max 3) |
| Agent returned malformed output | Logical | Re-run with explicit format instructions |
| Upstream stage not complete | Dependency | Skip, wait for next heartbeat |
| Token budget exceeded | Budget | Escalate to human via Telegram |
| Agent unreachable for 3+ cycles | Health | Escalate + attempt restart |
| Unrecognized error | Unknown | Escalate immediately |

---

## Budget Tiers (per task)

| Complexity | Token Budget | Review Loop Budget |
|-----------|-------------|-------------------|
| S (Small) | 50,000 | 20,000 |
| M (Medium) | 100,000 | 40,000 |
| L (Large) | 200,000 | 80,000 |
| XL (Extra Large) | 400,000 | 150,000 |

---

## Security Model

- All secrets via environment variables (never in state files)
- Agents run in isolated workspaces / Docker containers
- Git operations scoped to specific branches (never force-push to main/dev)
- CLI commands restricted via OpenClaw `gateway.nodes.denyCommands`
- State files are append-only for audit trail (no silent deletions)

---

## External Dependencies

| Service | Used By | Auth |
|---------|---------|------|
| Linear API | All agents | `LINEAR_API_KEY` |
| GitHub API / gh CLI | NightShift, PR Resolver, PR Review Bot, PR Automation | `GH_TOKEN` |
| Claude Code | NightShift, PR Resolver | `CLAUDE_CODE_OAUTH_TOKEN` |
| Telegram | Conductor (escalation), PR Resolver | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` |
| Slack | PR Review Bot | `SLACK_BOT_TOKEN` |
| OpenClaw Gateway | All agents | Local gateway token |
