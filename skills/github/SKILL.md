---
name: github-monitoring
description: Monitor PR status, CI pipelines, and review states across repos
---

# GitHub Monitoring Skill

Conductor monitors GitHub for PR status, review decisions, and CI results without modifying anything.

## Monitored Repositories
From PR Resolver config + PR Automation config:
- ruh-ai/strapi-service
- ruh-ai/hubspot-mcp
- ruh-ai/salesforce-mcp
- ruh-ai/sdr-backend
- ruh-ai/inbox-rotation-service
- ruh-ai/sdr-management-mcp
- ruh-ai/ruh-app-fe
- ruh-ai/agent-platform-v2
- ruh-ai/agent-gateway
- ruh-ai/communication-service
- ruh-ai/ai-proxy

## Status Checks

### PR Review Status
```bash
gh pr view {PR_NUMBER} --repo {REPO} --json state,reviews,statusCheckRollup
```

Interpret `reviews`:
- `APPROVED` → PR can merge, advance to PR Automation
- `CHANGES_REQUESTED` → needs PR Resolver
- `COMMENTED` → informational, may or may not need action
- No reviews → PR Review Bot webhook hasn't fired yet, or review pending

### CI Pipeline Status
```bash
gh pr checks {PR_NUMBER} --repo {REPO}
```

Interpret:
- All checks `pass` → CI green
- Any check `fail` → CI red, PR Resolver should diagnose
- Checks `pending` → wait, re-check next cycle

### PR Merge Status
```bash
gh pr view {PR_NUMBER} --repo {REPO} --json merged,closed
```
- `merged: true` → advance task to completion
- `closed: true, merged: false` → PR was closed without merge, investigate

## Rules
- Conductor only READS GitHub — never pushes, merges, or comments
- Use `gh` CLI (authenticated via GH_TOKEN)
- Cache PR status per cycle to avoid redundant API calls
