---
name: github-linear-automation
description: Automate QA and Prod releases by syncing Linear tickets to GitHub PRs. Use when asked to run a QA release, prod release, cherry-pick commits for Linear tickets, create release PRs, or check release status. Queries Linear for tickets in target status, scans GitHub repos for matching commits, cherry-picks onto a release branch, auto-resolves conflicts with Claude CLI, and opens PRs. Triggers on "qa release", "prod release", "release to QA", "release to prod", "cherry-pick tickets", "linear release".
---

# GitHub-Linear Automation

Automates the release workflow: Linear tickets → GitHub commits → cherry-pick → PR.

Supports **two release targets**:
- **QA Release** → cherry-picks to `qa` branch
- **Prod Release** → cherry-picks to `main` branch

## Quick Start

```bash
cd $PROJECT_DIR
source .venv/bin/activate

# Interactive — prompts for target
python main.py

# Or specify directly
python main.py --target qa
python main.py --target prod
```

> Set `PROJECT_DIR` to your local clone of the automation repo.

## What It Does

1. **Discover** — Queries Linear for tickets in target status
2. **Scan** — Searches configured repos for commits starting with ticket IDs
3. **Cherry-pick** — Creates `release/{qa|prod}-YYYY-MM-DD-HHMM` branch, applies commits
4. **Resolve Conflicts** — Uses Claude CLI to auto-resolve merge conflicts (optional)
5. **PR** — Opens/updates PRs with ticket summaries, commits, file changes, env vars
6. **Report** — Lists all Linear tickets considered, PRs created, resolved/unresolved conflicts

## Configuration

### Teams & Releases (`config/boards.yaml`)

```yaml
linear:
  teams:
    - RUH
    - SDR
    - RP
    - TT

# Release targets — each defines Linear statuses + GitHub settings
releases:
  qa:
    name: "QA Release"
    target_statuses:
      - name: "Ready to Deploy- QA"
    merged_transition:
      name: "In QA"
      ids:
        RUH: "In QA"
        SDR: "In QA"
        RP: "In QA"
        TT: "In QA"
    github:
      base_branch: qa
      source_branch: dev
      release_branch_prefix: "release/qa-"
      pr_labels:
        - qa-release

  prod:
    name: "Prod Release"
    target_statuses:
      - name: "Approved for Prod"
    merged_transition:
      name: "Released to Prod"
      ids:
        RUH: "Released to Prod"
        SDR: "Released to Prod"
        RP: "Released to Prod"
        TT: "Released to Prod"
    github:
      base_branch: main
      source_branch: qa
      release_branch_prefix: "release/prod-"
      pr_labels:
        - prod-release
```

### Repos (`config/repos.yaml`)

```yaml
commit_pattern: "([A-Z]+-\\d+)"       # Regex to extract Linear IDs
repositories:
  - name: your-repo-name
    type: backend
```

### Environment (`.env`)

```bash
LINEAR_API_KEY=lin_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_ORG=your-org
```

## Commands

| Command | Description |
|---------|-------------|
| `python main.py` | Interactive — prompts for qa/prod |
| `python main.py --target qa` | Run QA release pipeline |
| `python main.py --target prod` | Run Prod release pipeline |
| `python main.py -t qa --resolve-conflicts` | QA release with AI conflict resolution |

## Conflict Handling

Commits that fail to cherry-pick cleanly are **skipped** and logged. The PR body lists skipped commits with conflicting files. Use `--resolve-conflicts` to attempt automatic resolution via Claude CLI.

## Already-Merged Ticket Transitions

When commits are already in the target branch (skipped as "already merged"), their tickets are automatically transitioned:

- **QA Release** → Tickets move to "In QA"
- **Prod Release** → Tickets move to "Released to Prod"

## Project Structure

```
$PROJECT_DIR/
├── main.py                 # Entry point (--target qa|prod)
├── core/
│   ├── linear_client.py    # Linear API queries (GraphQL)
│   ├── commit_scanner.py   # Git log scanning (parallel)
│   ├── cherry_pick.py      # Branch + cherry-pick + push
│   ├── github_client.py    # PR creation
│   └── release_manager.py  # Orchestrator
├── config/
│   ├── boards.yaml         # Linear + GitHub settings per release
│   └── repos.yaml          # Repos to scan
└── logs/
    └── automation.log      # Run logs
```

## Running

Ensure venv is set up:

```bash
cd $PROJECT_DIR
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Then run
python main.py --target qa   # or prod
```

## Branch Scanning

Commits are scanned from specific source branches only:
- **QA release**: scans `dev` branch → cherry-picks to `qa`
- **Prod release**: scans `qa` branch → cherry-picks to `main`

This is configured in `config/boards.yaml` via `source_branch` setting.

## Two-Stage Workflow

The release process runs in two stages via separate cron jobs:

**Stage 1 — PR Creation** (`:00` for QA, `:30` for Prod)
- Runs the release pipeline
- Creates/updates PRs with cherry-picked commits

**Stage 2 — PR Review** (`:30` for QA, `:00` for Prod)  
- Uses `pr-review` skill to find open release PRs
- Spawns `merge-request-reviewer` to verify each PR
- Reports approve/reject verdict

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No tickets found | Check `target_statuses` names match your Linear workflow states exactly |
| No commits found | Verify commit messages start with ticket IDs (e.g., `RUH-123`) |
| Clone fails | Check `GITHUB_TOKEN` has repo access |
| PR creation fails | Ensure token has `repo` scope |
| Wrong branch | Verify `base_branch` in `releases.qa` or `releases.prod` |
| Linear API error | Verify `LINEAR_API_KEY` is valid and has read/write access |
