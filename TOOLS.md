# TOOLS.md — Conductor Available Tools

## Core Tools

### Linear API (via linear.sh skill)
- Query tickets by state, team, assignee
- Read ticket details, comments, linked issues
- Read ticket state transitions
- **Note:** Conductor reads but does NOT write to Linear — agents handle their own transitions

### GitHub CLI (gh)
- List PRs, check PR status and reviews
- Read CI/pipeline status
- Check branch existence
- **Note:** Conductor reads but does NOT push code or create PRs

### State Management (filesystem)
- Read/write `state/tasks/{TICKET-ID}.json`
- Read/write `state/agents/{agent}.json`
- Read/write `state/metrics/daily.json`
- Read/write `state/budget/{TICKET-ID}.json`

### Telegram Notifications
- Send escalation messages to configured chat
- Format: structured message with ticket ID, agent, failure reason, suggested action

### Docker (for NightShift)
- Check container health: `docker ps --filter name=nightshift`
- Read container logs: `docker logs nightshift --tail 50`
- Restart container: `docker restart nightshift`

### Process Management
- Check PR Review Bot server: `curl -s http://localhost:8000/health`
- Check OpenClaw gateway health: `curl -s http://127.0.0.1:18789/health`

---

## Tool Usage Rules

1. **Read-first:** Always read current state before making decisions
2. **Write-atomic:** Update state files completely, never partial writes
3. **No side effects:** Conductor tools are observational — agents perform mutations
4. **Escalation channel:** Telegram only — never post to Slack or GitHub directly
