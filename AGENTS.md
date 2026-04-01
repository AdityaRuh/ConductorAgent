# AGENTS.md — Conductor Agent Registry

This file maps every sub-agent that Conductor orchestrates. Each agent lives in its own cloned repository within this workspace.

---

## Pipeline Agents

### 1. Pathfinder 🧭
- **Repo:** `agents/pathfinder-agent/`
- **Type:** OpenClaw heartbeat agent
- **Interval:** Every 30 minutes
- **Watches:** Linear tickets in `Todo` state
- **Produces:** RCA (bugs) or TRD (features) + code change map posted as Linear comment
- **Transitions:** `Todo` → `In Progress`
- **Sub-agents:** ticket-classifier, rca-agent, trd-agent, repo-scanner, plan-writer
- **State file:** `agents/pathfinder-agent/memory/processed-issues.json`

### 2. NightShift 🌙
- **Repo:** `agents/NightShift/`
- **Type:** Python engine in Docker (continuous poll)
- **Interval:** Every 60 minutes
- **Watches:** Linear tickets in `Ready for Development` state
- **Requires:** Pathfinder plan comment on ticket
- **Produces:** Tests + implementation + GitHub PR
- **Transitions:** `Ready for Development` → `Require Changes` → `Code Review`
- **Sub-agents:** test-agent (Sentinel Guardian), dev-agent (TDD implementer)
- **State files:** `agents/NightShift/logs/processed_issues.json`, `agents/NightShift/logs/completed_repos.json`

### 3. PR Review Bot 🔍
- **Repo:** `agents/pr-review-bot/`
- **Type:** FastAPI webhook server
- **Trigger:** GitHub `pull_request` events (opened, synchronize, reopened)
- **Watches:** PR events via webhook
- **Produces:** Inline review comments on the PR
- **Transitions:** None (posts comments; PR Resolver acts on them)
- **Debounce:** 30 seconds (avoids duplicate synchronize events)
- **Skips:** Draft PRs, bot's own PRs

### 4. PR Resolver 🔧
- **Repo:** `agents/pr-resolver/`
- **Type:** OpenClaw heartbeat agent + Bash orchestrator
- **Interval:** Every 30 minutes
- **Watches:** Linear tickets in `Require Changes` state
- **Produces:** Code fixes for review comments + CI green
- **Transitions:** `Require Changes` → `Code Review`
- **Sub-agents:** 30 micro-agents (classifier, fixer, reviewer, CI observer, etc.)
- **State file:** `agents/pr-resolver/state/processed-comments.json`
- **Budget:** Max 3 fixes/PR/cycle, 10/cycle, 20/hour

### 5. PR Automation 🚀
- **Repo:** `agents/pr-automation/`
- **Type:** Python CLI (on-demand)
- **Trigger:** Manual or Conductor-initiated
- **Watches:** `Ready to Deploy - QA` or `Approved for Prod`
- **Produces:** Release branches with cherry-picked commits + release PRs
- **Transitions:** `Ready to Deploy - QA` → `In QA` / `Approved for Prod` → `Released to Prod`
- **Config:** `pr-automation/github-linear-automation/config/boards.yaml`

---

## The Review Loop (Agents 3 ↔ 4)

```
PR Review Bot posts review
        │
   Changes requested?
   ┌────YES────┐
   │           │
   ▼           │
PR Resolver    │
fixes code ────┘  (loop repeats)
   │
   └── PR Review Bot re-reviews on push
              │
           APPROVED ✓
              │
              ▼
       PR Automation (when ready)
```

**Conductor enforces:**
- Max 5 iterations of this loop per PR
- Max 3 CI repair attempts per iteration
- Budget tracking across all iterations
- Human escalation if limits hit

---

## Agent Health Monitoring

Conductor checks agent health every heartbeat by reading `state/agents/{agent}.json`:

| Condition | Status | Action |
|-----------|--------|--------|
| Last success < 1 cycle ago | `healthy` | No action |
| Last success 1-2 cycles ago | `degraded` | Log warning |
| Last success 3+ cycles ago | `unhealthy` | Escalate to Telegram |
| Consecutive failures >= 3 | `critical` | Escalate + pause routing |
