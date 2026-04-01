---
name: scan
description: Run the full NightShift pipeline — scan Linear for eligible tickets and process them
---

# /scan

Run the full NightShift pipeline autonomously.

## What to Do

Execute the complete pipeline described in CLAUDE.md:

1. **COLLECT** — Authenticate with Linear, fetch eligible tickets (Ready for Development, assigned to you), sort by priority
2. **PREPARE** — For each ticket: fetch comments, parse Pathfinder analysis, detect repos, clone/update repos, create worktrees
3. **EXECUTE** — For each ticket:
   - Transition to "In Development"
   - If complexity is L/XL and no children → decompose into subtasks first
   - Test Agent: write tests, commit
   - Dev Agent: implement fix until tests pass, commit
   - Push branch, create PR via `gh`
   - **Post comment on Linear ticket** with PR link, commits, files changed
   - Transition to "Code Review"

## Important

- Do NOT skip the Linear comment step. Always post PR links and change summary on the ticket.
- Do NOT skip the state transition. Always move to "In Development" when starting and "Code Review" when done.
- If a repo fails, note it on the ticket and continue with other repos.
- If all repos fail, move ticket back to "Ready for Development" for retry.

## If Running on a Server with the Python Engine

```bash
cd ~/NightShift/engine
python3 run_once.py
```

## If Running via OpenClaw (this session)

Execute the pipeline steps directly using bash (curl for Linear API, git for repos, gh for PRs). Follow the exact steps in CLAUDE.md.
