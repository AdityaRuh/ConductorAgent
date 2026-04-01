---
name: pr-review
description: Review open PRs targeting qa or main branch. Spawns merge-request-reviewer to verify changes and provide approval recommendations. Use when asked to review release PRs, check open PRs for qa/main, or verify cherry-pick PRs.
---

# PR Review Skill

Reviews open PRs targeting `qa` or `main` branch by spawning the `merge-request-reviewer` agent.

## Usage

```bash
# Review QA PRs
/pr-review qa

# Review Prod PRs  
/pr-review prod
```

## What It Does

1. **Find PRs** — Lists open PRs targeting the specified branch (`qa` or `main`)
2. **Filter** — Only includes PRs with `qa-release` or `prod-release` labels
3. **Review** — Spawns `merge-request-reviewer` to analyze each PR
4. **Report** — Returns verdict (approve/reject) with reasons for each PR

## Implementation

### Step 1: Find Open Release PRs

```bash
# For QA
gh pr list --repo <org>/<repo> --base qa --label qa-release --state open --json number,url,title

# For Prod
gh pr list --repo <org>/<repo> --base main --label prod-release --state open --json number,url,title
```

### Step 2: Spawn Reviewer

For each PR found, spawn `merge-request-reviewer`:

```
sessions_spawn(
  label="merge-request-reviewer",
  task="Review this PR: <URL>. Check for broken conflict resolutions, syntax errors, and provide approval recommendation.",
  mode="run"
)
```

### Step 3: Report Results

Format results as:

```
## PR Review — QA Branch

### ✅ Approved
| Repo | PR | Notes |
|------|-----|-------|
| repo-name | #123 | Clean changes |

### ❌ Needs Work
| Repo | PR | Issues |
|------|-----|--------|
| repo-name | #456 | Broken conflict resolution in file.py |

### No PRs Found
If no open release PRs exist, report: "No open PRs for review on {branch} branch."
```

## Repos to Scan

**Only scan repos listed in `$PROJECT_DIR/config/repos.yaml`.**

Do NOT scan all repos in the GitHub org. Read repos.yaml first and iterate through that list only:

```bash
# Extract repo names from repos.yaml
grep "name:" $PROJECT_DIR/config/repos.yaml | awk '{print $2}'
```

Then for each repo in that list, check for open PRs.

## Cron Integration

This skill is triggered by scheduled cron jobs:
- `qa-review`: Runs at `:30` after QA PR creation
- `prod-review`: Runs at `:00` after Prod PR creation
