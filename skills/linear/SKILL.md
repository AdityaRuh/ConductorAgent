---
name: linear-pipeline
description: Query Linear for pipeline ticket states and track transitions
---

# Linear Pipeline Skill

Conductor uses Linear as the shared state bus for all agents. This skill defines how to query and interpret ticket states.

## Ticket State Mapping

| Linear State | Pipeline Stage | Owner |
|-------------|---------------|-------|
| Todo | Intake | Pathfinder |
| In Progress | Plan posted, awaiting human approval | Human |
| Ready for Development | Approved for implementation | NightShift |
| In Development | Code being written or PR under review | NightShift / PR Resolver |
| Code Review | PR review cycle active | PR Review Bot / PR Resolver |
| Ready to Deploy - QA | Approved for QA release | PR Automation |
| In QA | QA testing in progress | Human/QA team |
| Approved for Prod | Ready for production release | PR Automation |
| Released to Prod | Done | Archive |

## Query Patterns

### Find new tickets for pipeline
```graphql
issues(filter: {
  state: { name: { eq: "Todo" } },
  team: { key: { in: ["RP", "SDR", "RUH", "TT"] } }
}) { nodes { id identifier title priority labels { nodes { name } } } }
```

### Find tickets at each stage
Use same pattern with state name: "Ready for Development", "In Development", "Code Review", etc.

### Check if Pathfinder comment exists
```graphql
issue(id: "ISSUE_ID") {
  comments { nodes { body user { name } } }
}
```
Look for comment from Pathfinder agent (contains "## Root Cause Analysis" or "## Technical Requirements Document").

### Find PR link on ticket
Check ticket attachments, comments with GitHub PR URLs, or external links.

## Teams Configuration
From `pr-automation/github-linear-automation/config/boards.yaml`:
- **RP** — Main product team
- **SDR** — Sales development
- **RUH** — Core platform
- **TT** — Tooling/testing

## Rules
- Conductor READS Linear but never WRITES (agents handle their own transitions)
- One exception: if a task is CANCELLED by Conductor, it may add a comment explaining why
- Always verify Linear state matches expected state before routing
