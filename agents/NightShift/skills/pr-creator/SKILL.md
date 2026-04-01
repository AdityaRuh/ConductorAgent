---
name: pr-creator
description: Push branch, create PR via GitHub CLI, comment on Linear ticket, and transition to Code Review
---

# PR Creator

Handles the final steps after implementation: push, PR, Linear comment, state transition.

## How to Execute

### Step 1: Verify Changes Exist

```bash
cd "$WORKTREE"
git diff HEAD~1 --stat
```

If no changes/commits, stop — nothing to ship.

Check for `CLAUDE_UNABLE.md` — if it exists, the agent couldn't fix the issue. Note this on the ticket and stop.

### Step 2: Push the Branch

```bash
BRANCH="claude/$(echo $TICKET_ID | tr '[:upper:]' '[:lower:]')"
git push origin "$BRANCH"
```

If push fails due to auth, stop and inform the user.

### Step 3: Create GitHub PR

```bash
# Detect the GitHub repo from remote URL
REMOTE_URL=$(git remote get-url origin)
GH_REPO=$(echo "$REMOTE_URL" | sed -E 's/.*[:/]([^/]+\/[^/]+?)(\.git)?$/\1/')

# Get commit messages for PR body
COMMITS=$(git log --format="- %s" origin/${TARGET_BRANCH:-dev}..HEAD)
FILES=$(git diff origin/${TARGET_BRANCH:-dev}..HEAD --name-only)
DIFF_STAT=$(git diff origin/${TARGET_BRANCH:-dev}..HEAD --stat)

gh pr create \
  --repo "$GH_REPO" \
  --base "${TARGET_BRANCH:-dev}" \
  --head "$BRANCH" \
  --title "$TICKET_ID: $TITLE" \
  --body "## Summary
$COMMITS

## Ticket
[$TICKET_ID]($TICKET_URL)

## Changes Made
$(echo "$FILES" | sed 's/^/- `/' | sed 's/$/`/')

\`\`\`
$DIFF_STAT
\`\`\`

---
*Automated by NightShift*"
```

Capture the PR URL from the output. If `gh` fails, construct manual URL:
```
https://github.com/$GH_REPO/compare/${TARGET_BRANCH:-dev}...$BRANCH?expand=1
```

### Step 4: Comment on Linear Ticket (CRITICAL)

**You MUST always post a comment on the Linear ticket.** This is how the team knows what happened.

```bash
# Build comment body
COMMENT="Development complete. Branch and PR created automatically.

**Branch:** \`$BRANCH\`
**PR:** $PR_URL

### Changes Summary
$COMMITS

**Files changed:**
$(echo "$FILES" | sed 's/^/- \`/' | sed 's/$/\`/')

\`\`\`
$DIFF_STAT
\`\`\`

---
*Processed by NightShift*"

# Post to Linear
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"mutation(\$issueId: String!, \$body: String!) { commentCreate(input: { issueId: \$issueId, body: \$body }) { success } }\", \"variables\": {\"issueId\": \"$ISSUE_ID\", \"body\": $(echo "$COMMENT" | jq -Rs .)}}"
```

### Step 5: Transition to "Code Review"

```bash
# Get team states
STATES=$(curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"query(\$id: String!) { team(id: \$id) { states { nodes { id name type } } } }\", \"variables\": {\"id\": \"$TEAM_ID\"}}")

# Find "Code Review" state
STATE_ID=$(echo "$STATES" | jq -r '.data.team.states.nodes[] | select(.name == "Code Review") | .id')

# Transition
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"mutation(\$id: String!, \$stateId: String!) { issueUpdate(id: \$id, input: { stateId: \$stateId }) { success } }\", \"variables\": {\"id\": \"$ISSUE_ID\", \"stateId\": \"$STATE_ID\"}}"
```

### Step 6: Clean Up Worktree

```bash
cd "$REPO_DIR"
git worktree remove "$WORKTREE" --force 2>/dev/null || true
```

## If Multiple Repos Had PRs

When a ticket spans multiple repos, the comment should include ALL PRs:

```
**PR (agent-platform-v2):** https://github.com/ruh-ai/agent-platform-v2/pull/367
**PR (agent-gateway):** https://github.com/ruh-ai/agent-gateway/pull/236
```

## If a Repo Failed or Doesn't Exist

Note it in the comment:
```
**agent-builder-service:** Repo does not exist on GitHub (404). Needs clarification.
```

And do NOT mark the ticket as fully complete — note partial completion.

## Error Handling

| Situation | Action |
|---|---|
| No changes to push | Skip this repo, move to next |
| CLAUDE_UNABLE.md exists | Note on ticket, don't create PR |
| Push fails (auth) | Stop, inform user |
| `gh` not installed | Construct manual compare URL |
| PR already exists for branch | Note it, don't create duplicate |
| Linear comment fails | Log warning, continue (non-critical) |
| State transition fails | Log warning, continue |

## Safety Rules

- Never modify `.env`, secrets, or credentials
- Never force-push to `dev` or `main`
- Always branch from `dev` (or `main`/`master` if `dev` doesn't exist)
- Never push directly to `dev` or `main` — always use PR
