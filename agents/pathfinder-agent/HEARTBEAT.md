# HEARTBEAT.md — Pathfinder Autonomous Cycle

## Purpose

Every 30 minutes: scan Linear teams, find Todo issues assigned to the user, classify, analyze, plan, post, transition. No fluff.

---

## Checklist (run every heartbeat)

### 1. Scan Linear for Todo Issues

Fetch all issues in Todo status **assigned to you** across all Ruh AI Linear teams.

```
→ Run: linear.sh my-todos
→ Skip issues already processed (check memory/processed-issues.json)
→ Queue unprocessed issues for analysis
```

If no new Todo issues assigned to the user → `HEARTBEAT_OK`

### 2. For Each Unprocessed Issue

#### 2a. Read the Issue
- Use `linear.sh issue <ID>` to fetch full issue data
- Read title, description, comments, linked issues, parent issue
- Read state, priority, labels, team, project
- Check for attachments (error logs, screenshots, specs)

#### 2b. Classify: Bug or Feature
- Bug → proceed to RCA flow
- Feature → proceed to TRD flow
- Ambiguous → default to feature

#### 2c. Generate Analysis

**Bug path:**
1. Load `skills/rca/SKILL.md`
2. Identify symptom from issue description
3. Consult `knowledge-graph/` to trace probable cause
4. Go into affected repo(s) — read actual code to confirm root cause
5. Generate RCA using `templates/rca-template.md`

**Feature path:**
1. Load `skills/trd-generation/SKILL.md`
2. Extract requirements from issue description
3. Consult `knowledge-graph/` to identify affected services
4. Go into affected repo(s) — identify specific files and functions
5. Generate TRD using `templates/trd-template.md`

#### 2d. Identify Code Changes
1. Load `skills/code-change-detection/SKILL.md`
2. Read `knowledge-graph/connections/service-map.md` for cross-repo impacts
3. Read relevant `knowledge-graph/repos/*.md` files
4. Go into each affected repo — find exact files, functions, classes
5. Document: file path, function/class, what changes, why

#### 2e. Assemble Plan
1. Combine RCA/TRD + code changes into structured plan
2. Use `templates/plan-template.md` format
3. Include complexity estimate (S/M/L/XL)

#### 2f. Post to Linear
1. Add plan as a comment on the issue:
   ```bash
   linear.sh comment <ID> "plan content here"
   ```
2. Transition issue status to In Progress:
   ```bash
   linear.sh status <ID> progress
   ```
3. Record in `memory/processed-issues.json`:
   ```json
   {
     "ABC-123": {
       "processed": "2026-03-25T10:30:00Z",
       "classification": "feature",
       "repos_affected": ["agent-gateway", "communication-service"],
       "complexity": "M"
     }
   }
   ```

### 3. Post-Cycle Check

- Any issues that failed analysis? → Log error, retry next cycle
- Knowledge graph gaps discovered? → Note them for `/graph` update

---

## Response Format

Nothing to do:
```
HEARTBEAT_OK — No new Todo issues found
```

Issues processed:
```
Pathfinder — Processed 3 issues

RP-400 (bug) → RCA posted, moved to In Progress
   Repos: agent-gateway, communication-service | Complexity: M

RP-401 (feature) → TRD posted, moved to In Progress
   Repos: agent-platform-v2 | Complexity: S

RP-402 (feature) → Analysis incomplete — missing acceptance criteria
   Action: Added comment requesting clarification, left in Todo
```

Error:
```
RP-403 — Failed to analyze: could not access repo agent-platform-v2
   Action: Will retry next heartbeat
```
