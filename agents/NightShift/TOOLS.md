# TOOLS.md — NightShift

## Docker (Primary Interface)

NightShift runs inside a Docker container named `nightshift`.

```bash
# Run full pipeline (scan + process all eligible tickets)
docker exec nightshift python3 engine/run_once.py

# View logs
docker logs nightshift --tail 50

# Search logs for specific ticket
docker logs nightshift 2>&1 | grep RUH-XXX

# Restart container
cd ~/NightShift && docker compose restart

# Rebuild and restart (after code changes)
cd ~/NightShift && docker compose up --build -d
```

## Claude Code (`claude`)

Available inside the container. Used internally by Test Agent and Dev Agent.

```bash
# Check auth
docker exec nightshift claude auth status

# Test connectivity
docker exec nightshift claude -p "Say hello" --output-format text
```

## GitHub CLI (`gh`)

Available inside the container for PR management.

```bash
# List PRs
docker exec nightshift gh pr list --repo ruh-ai/REPO

# Check PR status
docker exec nightshift gh pr view NUMBER --repo ruh-ai/REPO
```

## Git

Available inside the container for repo operations.

```bash
# Check cloned repos
docker exec nightshift ls /app/repos/

# Check worktrees
docker exec nightshift ls /app/repos/REPO/.worktrees/

# Check branches
docker exec nightshift git -C /app/repos/REPO branch -a
```

## Linear API

Accessed via Python's `LinearClient` class (GraphQL). No CLI tool — all API calls are in the engine.

## Sentinel Guardian

Test skills mounted read-only at `/app/sentinel-skills/` inside the container. Skills come from the host at `~/.openclaw/workspace/sentinel-guardian/skills/`.
