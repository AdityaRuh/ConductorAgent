# NightShift

> Autonomous development agent that picks up tickets, writes tests, implements fixes, and ships PRs — while you sleep.

NightShift processes Linear tickets end-to-end using Test-Driven Development with Sentinel Guardian test methodology. It runs inside Docker, polls Linear for eligible tickets, and produces ready-to-review pull requests.

---

## How It Works

```
  Linear Board               Pathfinder (upstream)            NightShift
  ────────────               ────────────────────             ──────────
  Ticket created      --->   Analyzes ticket
  in "Todo"                  Writes RCA (bug) or
                             TRD (feature)
                             Posts comment with analysis
                             Moves to "Ready for Dev"  --->  Picks up ticket
                                                             Filters repos (LLM)
                                                             Decomposes if L/XL (*)
                                                             Writes tests (Sentinel)
                                                             Implements fix (TDD)
                                                             Creates PR with summary
                                                             Moves to "Code Review"

(*) Complex tickets (L/XL) are automatically broken into subtasks.
    Each subtask gets its own test + implementation cycle.
```

---

## Pipeline (6 Phases)

### Phase 1: COLLECT

```
Linear API
  |
  |-- Authenticate as bot user (get viewer ID)
  |-- Scan all teams the API key has access to
  |-- Fetch tickets in "Ready for Development" state
  |     (fallback: unstarted/started types)
  |-- Exclude already-processed (tracked in processed_issues.json)
  |-- Exclude tickets labeled "claude-processing" or "claude-done"
  '-- Sort by priority: Urgent > High > Medium > Low > None
```

Priority mapping: `{1: Urgent, 2: High, 3: Medium, 4: Low, 0: None}`

### Phase 2: PREPARE

```
For each ticket:
  |
  |-- Fetch comments from Linear
  |-- Find Pathfinder comment (marker: "Pathfinder Analysis")
  |-- Parse Pathfinder analysis:
  |     |-- Classification: BUG / FEATURE / TASK
  |     |-- Complexity: S / M / L / XL
  |     |-- Repos affected (with notes: "Primary Changes", "No Changes Needed")
  |     |-- Code changes table (repo, file, function, change type, description)
  |     '-- File hints (paths mentioned in analysis)
  |
  |-- LLM Repo Filter (repo_filter.py)
  |     |-- Sends full Pathfinder text + repo list to Claude CLI
  |     |-- Asks: "Which repos actually need code changes?"
  |     |-- Removes repos that need no modifications
  |     |-- Semantic understanding (not string matching)
  |     |-- 30s timeout, max-turns 2, falls back to full list on failure
  |     '-- Skipped if only 1 repo
  |
  |-- Enrich ticket context (7 parallel API calls):
  |     |-- Issue state + labels
  |     |-- Discussion thread (up to 50 comments)
  |     |-- Sub-issues and statuses
  |     |-- Parent ticket (for sub-tasks)
  |     |-- Related issues (blocks, blocked-by, duplicates)
  |     |-- Attachments
  |     |-- Acceptance criteria (parsed from description)
  |     '-- File hints (extracted from description + comments)
  |
  |-- Decompose complex tickets (task_decomposer.py):
  |     |-- Triggered when Pathfinder complexity is L or XL
  |     |-- Skipped if ticket already has children (no re-decomposition)
  |     |-- Calls Claude CLI (max-turns 3, 60s timeout) to analyze
  |     |     Pathfinder and propose 2-7 focused subtasks
  |     |-- Creates subtasks in Linear as children of parent ticket
  |     |-- Transitions each subtask to "Ready for Development"
  |     |-- Comments on parent with subtask list
  |     |-- Parent marked as processed; subtasks queued for execution
  |     '-- On failure: falls back to processing parent as single task
  |
  '-- Clone/update all unique repos in parallel (up to 4 workers)
        |-- Check REPO_MAP first, then auto-clone from GitHub
        |-- Pull latest from TARGET_BRANCH (dev/main/master)
        '-- Create isolated git worktree: .worktrees/claude/{ticket-id}
```

#### Task Decomposition (L/XL Tickets)

When Pathfinder marks a ticket as **L** or **XL** complexity, NightShift automatically decomposes it into smaller subtasks before processing. This prevents single Claude Code sessions from hitting max-turns or timeout limits on large tasks.

```
Parent Ticket (XL) ---- "Rebuild the authentication system"
  |
  | Claude CLI analyzes Pathfinder code changes table
  | and proposes focused subtasks
  |
  +-- Subtask 1: [1/4] Add JWT token validation schema
  |     '-- Own Test Agent (30 turns) + Dev Agent (30 turns) + PR
  +-- Subtask 2: [2/4] Update session middleware
  |     '-- Own Test Agent (30 turns) + Dev Agent (30 turns) + PR
  +-- Subtask 3: [3/4] Migrate user model to new auth flow
  |     '-- Own Test Agent (30 turns) + Dev Agent (30 turns) + PR
  '-- Subtask 4: [4/4] Update API endpoints for new auth
        '-- Own Test Agent (30 turns) + Dev Agent (30 turns) + PR
```

**Error handling:** Every failure path falls back to processing the parent as a single task. If a subtask fails during execution, it is moved back to "Ready for Development" and retried on the next scan.

### Phase 3: SCOPE

```
Ticket Scope Resolution (via DeveloperSkill):
  |
  |-- "normal" --- standalone ticket, no children
  |     '-- Process normally
  |
  |-- "parent_with_subtasks" --- has child issues
  |     |-- Identify sub-tasks assigned to OTHER developers
  |     |-- Exclude their scope from implementation
  |     '-- Only implement unassigned scope + own sub-tasks
  |
  '-- "subtask" --- is a child of a parent ticket
        |-- Fetch parent ticket for context
        '-- Only implement THIS sub-task's scope
```

Repo resolution priority: Pathfinder repos > `repo:` labels > GitHub URLs in description > parent ticket repos > project name > team key fallback.

### Phase 4: TEST (Test Agent)

```
For each repo (parallel, up to MAX_CONCURRENT_REPOS workers):
  |
  |-- Detect stack from project files:
  |     Backend:   requirements.txt, pyproject.toml, go.mod, Cargo.toml, pom.xml, Gemfile
  |     Frontend:  next.config.*, vite.config.*, angular.json, svelte.config.js
  |     Fullstack: both signals present
  |     (also checks package.json deps: react, next, vue, angular, svelte, nuxt)
  |
  |-- Load Sentinel Guardian skills for detected stack:
  |     Backend (9):   test-setup, unit-tests, integration-tests, contract-tests,
  |                    security-tests, resilience-tests, smoke-tests, e2e-api-tests, test-review
  |     Frontend (4):  test-setup, unit-tests, e2e-browser-tests, test-review
  |     Fullstack (10): all backend + e2e-browser-tests
  |
  |-- Build single test prompt (all skills concatenated):
  |     |-- test-agent.md definition
  |     |-- Ticket context (description, criteria, Pathfinder, comments, hints)
  |     |-- All applicable Sentinel skill instructions
  |     '-- Critical rules (tests only, 1 per criterion, follow patterns)
  |
  '-- Spawn Claude Code session:
        |-- Reads the codebase and existing test patterns
        |-- Writes tests covering: main behavior, each AC, edge cases
        |-- Commits: test(TICKET-ID): add tests for <title>
        '-- Max 30 turns, 15-minute timeout
```

Tests are written BEFORE implementation. They define the contract. The Dev Agent must make them pass without modifying test files.

### Phase 5: IMPLEMENT (Dev Agent)

```
Same worktree as Test Agent:
  |
  |-- Build implementation prompt:
  |     |-- dev-agent.md definition
  |     |-- Pathfinder RCA/TRD as primary source of truth
  |     |-- Code changes scoped to current repo only:
  |     |     |-- "Code Changes for This Repo" --- what to modify
  |     |     '-- "Code Changes in Other Repos" --- read-only context
  |     |-- Scope restrictions (sub-task exclusions if applicable)
  |     |-- Acceptance criteria + discussion thread
  |     '-- Developer skill instructions (TDD workflow from SKILL.md)
  |
  '-- Spawn Claude Code session:
        |-- Reads test files committed by Test Agent
        |-- Runs tests --- confirms they FAIL (red)
        |-- Implements fix following Pathfinder code changes table
        |-- Runs tests --- iterates until they PASS (green)
        |-- Runs full test suite --- checks for regressions
        |-- Commits:
        |     TICKET-ID: <ticket title>
        |
        |     <2-3 sentence summary of changes>
        |
        |     Resolves: TICKET-ID
        '-- If stuck, creates CLAUDE_UNABLE.md explaining why
```

Critical: Dev Agent NEVER edits test files. Tests are the contract.

### Phase 6: SHIP

```
For each repo with commits:
  |
  |-- Generate change summary:
  |     |-- Commit messages (git log base..HEAD)
  |     |-- Diff stats (files changed, insertions, deletions)
  |     |-- Environment change detection:
  |           |-- Modified .env* or docker-compose* files
  |           |-- New env var references: os.environ, os.getenv (Python)
  |           |-- New env var references: process.env (Node.js)
  |           '-- New .env file entries (KEY=value patterns)
  |
  |-- Push branch: claude/{ticket-id} --> origin
  |
  |-- Create GitHub PR:
  |     |-- Title: TICKET-ID: <ticket title>
  |     |-- Base: dev (configurable via TARGET_BRANCH)
  |     |-- Body:
  |     |     ## Summary
  |     |     <commit messages>
  |     |
  |     |     ## Ticket
  |     |     [TICKET-ID](url)
  |     |
  |     |     ## Changes Made
  |     |     <file list + diff stats>
  |     |
  |     |     ## Acceptance Criteria
  |     |     <checkboxes parsed from ticket description>
  |     |
  |     |     ## Environment Changes (if any)
  |     |     <detected env file changes + new env variables>
  |     |
  |     '-- Fallback: manual compare URL if gh CLI fails
  |
  '-- Clean up worktree

After all repos complete:
  |
  |-- Transition ticket to "Code Review"
  |-- Comment on ticket:
  |     Development complete. Branch and PR created automatically.
  |
  |     **Branch:** claude/{ticket-id}
  |     **PR:** <url>
  |
  |     ### Changes Summary
  |     <commit messages + files changed + diff stats>
  |
  |     ### Environment Changes (if any)
  |     <detected changes>
  |
  |     Changes were committed and pushed. Ticket moved to Code Review.
  |
  '-- Mark as processed (won't pick up again)
```

---

## Architecture

```
+-------------------------------------------------------------------+
|                       NightShift Pipeline                         |
|                                                                   |
|  +-----------+   +------------+   +-------------+   +---------+  |
|  |  COLLECT  |-->|  PREPARE   |-->|  DECOMPOSE  |-->|  SCOPE  |--+
|  |           |   |            |   | (L/XL only) |   |         |  |
|  | Linear    |   | Pathfinder |   |             |   | normal/ |  |
|  | tickets   |   | parse +   |   | Claude CLI  |   | parent/ |  |
|  | sorted by |   | LLM repo  |   | breaks into |   | subtask |  |
|  | priority  |   | filter +  |   | 2-7 subtasks|   |         |  |
|  +-----------+   | clone     |   | in Linear   |   +---------+  |
|                  +------------+   +-------------+        |       |
|                                                          |       |
|                          +-------------------------------+       |
|                          |                                       |
|                          v                                       |
|              +-----------+-----------+                            |
|              | Per Repo (parallel)   |                            |
|              |                       |                            |
|              |  +------------------+ |                            |
|              |  |   TEST AGENT     | |   Max 30 turns            |
|              |  |   (Sentinel)     | |   15 min timeout          |
|              |  +--------+---------+ |                            |
|              |           |           |                            |
|              |  +--------v---------+ |                            |
|              |  |   DEV AGENT      | |   Max 30 turns            |
|              |  |   (TDD impl)     | |   15 min timeout          |
|              |  +--------+---------+ |                            |
|              |           |           |                            |
|              |  +--------v---------+ |                            |
|              |  | SUMMARY + PUSH   | |   Commits, diff stats,   |
|              |  | + CREATE PR      | |   env change detection   |
|              |  +------------------+ |                            |
|              +-----------+-----------+                            |
|                          |                                       |
|              +-----------v-----------+                            |
|              | Update Linear ticket  |                            |
|              | Branch + PR + Summary |                            |
|              | Move to Code Review   |                            |
|              +-----------------------+                            |
+-------------------------------------------------------------------+

Concurrency:
  Tickets  --->  ThreadPoolExecutor (MAX_CONCURRENT_TICKETS, default: 2)
  Repos    --->  ThreadPoolExecutor (MAX_CONCURRENT_REPOS, default: 3)

Complexity handling:
  S/M tickets  --->  Processed directly (single Test + Dev session)
  L/XL tickets --->  Decomposed into subtasks, each processed individually
```

### Ticket Lifecycle

```
  Backlog / Todo
       |
       v
  Pathfinder analyzes (writes RCA or TRD comment)
       |
       v
  Ready for Development  <-- NightShift picks up here
       |
       +-- Complexity S/M: process directly
       |         |
       |         v
       |    In Development    <-- NightShift moves here when starting
       |         |
       |         v
       |    Code Review       <-- NightShift moves here when PR is created
       |
       +-- Complexity L/XL: decompose first
                 |
                 v
            In Development    <-- Parent moved here
                 |
                 +-- Subtask 1 --> Ready for Dev --> In Dev --> Code Review
                 +-- Subtask 2 --> Ready for Dev --> In Dev --> Code Review
                 '-- Subtask N --> Ready for Dev --> In Dev --> Code Review
       |
       v
  Ready to Deploy - DEV  <-- After human review approval
       |
       v
  (QA --> Prod flow)
```

---

## Components

### Core Orchestrator (`engine/lib/core.py`)
Three-phase processing engine with parallel execution:
- **Phase 1 (COLLECT):** Fetch, filter, sort tickets by priority
- **Phase 2 (PREPARE):** Parse Pathfinder, LLM-filter repos, decompose L/XL tickets, clone in parallel
- **Phase 3 (EXECUTE):** Process tickets in parallel, repos in parallel within each ticket
- **Task Decomposition:** L/XL tickets are broken into subtasks and queued for individual processing
- **Change Summary:** Extracts commit messages, diff stats, detects env changes
- **PR Creation:** Structured PR body with summary, changes, acceptance criteria, env changes
- **`gh` Fallback:** Returns manual compare URL when `gh pr create` fails

### Linear Client (`engine/lib/linear_client.py`)
GraphQL API client for all Linear operations:
- Fetch viewer, teams, issues (with labels, project, state)
- Issue state transitions, comment creation
- Children/parent fetching (with assignees for scope resolution)
- Sub-issue creation (for task decomposition)
- Relations, attachments

### Developer Skill (`engine/skills/developer_skill.py`)
Intelligence layer between ticket fetching and Claude Code:
- Resolves ticket scope: `normal` | `parent_with_subtasks` | `subtask`
- Resolves repos: Pathfinder > labels > URLs > parent > project > team key
- Detects stack: `backend` | `frontend` | `fullstack`
- Builds repo-scoped prompts for Test Agent and Dev Agent
- Enriches context with sub-issues, relations, acceptance criteria

### Sentinel Integration (`engine/skills/sentinel_integration.py`)
Loads Sentinel Guardian test skills based on detected stack:
- **Backend:** 9 skills (test-setup, unit, integration, contract, security, resilience, smoke, e2e-api, test-review)
- **Frontend:** 4 skills (test-setup, unit, e2e-browser, test-review)
- **Fullstack:** 10 skills (all backend + e2e-browser)
- Only loads skills that exist on disk, silently skips missing ones
- Concatenates all applicable skills into a single test prompt

### Ticket Enricher (`engine/skills/ticket_enricher.py`)
Deep context extraction from Linear (7 parallel API calls):
- Discussion thread (up to 50 comments with authors and dates)
- Sub-issues, parent context, relations, attachments
- Acceptance criteria parsing (supports `## Acceptance Criteria`, `## AC`, `## Requirements`, checkboxes, bullets, numbered lists)
- File hints extracted from descriptions and comments

### Pathfinder Parser (`engine/skills/pathfinder_parser.py`)
Extracts structured data from Pathfinder analysis comments:
- Classification (`BUG` / `FEATURE` / `TASK`), complexity (`S` / `M` / `L` / `XL`)
- Affected repos with contextual notes per repo
- Code changes table (repo, file, function, change type, description)
- Implementation order, file hints

### Task Decomposer (`engine/skills/task_decomposer.py`)
Automatically breaks complex tickets (L/XL) into focused subtasks before processing:
- **Gate check:** Only triggers when Pathfinder complexity is L or XL AND ticket has no existing children
- **Decomposition:** Lightweight Claude CLI call (max-turns 3, 60s timeout) analyzes Pathfinder code changes table and proposes 2-7 independently implementable subtasks
- **Creation:** Creates subtasks in Linear as children, assigns to bot, transitions to "Ready for Development"
- **Error handling:** Every failure path falls back to processing the parent as a single task. Subtasks that fail during execution are moved back to "Ready for Development" for retry on next scan

### LLM Repo Filter (`engine/skills/repo_filter.py`)
Lightweight Claude CLI call (max-turns 2, 30s timeout) that reads the Pathfinder analysis and determines which repos actually need code changes. Uses semantic understanding, not string matching. Falls back to full list on failure. Skipped if only 1 repo.

---

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/Rishabh-Kala-ruh/NightShift.git
cd NightShift
cp .env.example .env
# Edit .env with your credentials
```

### 2. Deploy

```bash
docker compose up -d --build

# Authenticate Claude Code (one-time)
docker exec -it nightshift claude setup-token

# Verify
docker exec nightshift claude auth status
docker logs nightshift --tail 20
```

### 3. Run

```bash
# Single scan (process all eligible tickets once)
docker exec nightshift python3 engine/run_once.py

# View logs
docker logs nightshift --tail 50

# Search for specific ticket
docker logs nightshift 2>&1 | grep RUH-XXX
```

The container runs `engine/main.py` by default, which polls every `POLL_INTERVAL_MINUTES` (default: 60).

---

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LINEAR_API_KEY` | Linear API key | Required |
| `GITHUB_ORG` | GitHub organization | `ruh-ai` |
| `TARGET_BRANCH` | Base branch for PRs | `dev` |
| `GH_TOKEN` | GitHub Personal Access Token | Required |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth token | Required |
| `MAX_CONCURRENT_TICKETS` | Parallel ticket limit | `2` |
| `MAX_CONCURRENT_REPOS` | Parallel repos per ticket | `3` |
| `POLL_INTERVAL_MINUTES` | Scan frequency (minutes) | `60` |
| `CLAUDE_CMD` | Claude CLI command | `claude` |
| `REPOS_DIR` | Where repos are cloned | `./repos` |
| `LOGS_DIR` | Log file directory | `./logs` |
| `REPO_MAP` | JSON map of repo name to local path | `{}` |
| `SENTINEL_SKILLS_PATH` | Sentinel Guardian skills directory | Auto-detected |

---

## Docker Setup

**Base image:** `python:3.12-slim`

**Installed tools:** git, openssh-client, curl, GitHub CLI (`gh`), Node.js 20, Claude Code (`@anthropic-ai/claude-code`)

**Volumes:**
- `repos-data` --- cloned repositories (`/app/repos`)
- `logs-data` --- automation logs (`/app/logs`)
- `claude-data` --- Claude Code config (`/root/.claude`)
- `gh-data` --- GitHub CLI auth (`/root/.config/gh`)
- SSH key mounted read-only for git operations
- Sentinel skills mounted read-only at `/app/sentinel-skills`

**Git identity:** `NightShift Bot <nightshift@ruh-ai.com>`

---

## Project Structure

```
NightShift/
|-- IDENTITY.md              # Agent identity
|-- SOUL.md                  # Core behavior + hard rules
|-- ARCHITECTURE.md          # System design
|-- TOOLS.md                 # Available tools reference
|-- AGENTS.md                # Sub-agent overview
|-- agents/                  # OpenClaw agent definitions
|   |-- test-agent.md
|   '-- dev-agent.md
|-- skills/                  # OpenClaw skill definitions
|   |-- ticket-scanner/
|   |-- pathfinder-reader/
|   |-- test-generator/
|   |-- implementer/
|   |-- pr-creator/
|   '-- linear/              # Linear CLI tool (from ClawHub)
|       |-- SKILL.md
|       '-- scripts/linear.sh
|-- commands/                # OpenClaw chat commands
|   |-- scan.md
|   |-- status.md
|   '-- check.md
|-- engine/                  # Python execution engine
|   |-- lib/
|   |   |-- config.py        # Environment config loader
|   |   |-- core.py          # 3-phase orchestrator + PR creation
|   |   '-- linear_client.py # Linear GraphQL API client
|   |-- skills/
|   |   |-- agents/
|   |   |   |-- test-agent.md        # Test Agent definition
|   |   |   '-- dev-agent.md         # Dev Agent definition
|   |   |-- developer-skill/
|   |   |   '-- SKILL.md             # TDD workflow instructions
|   |   |-- ticket_enricher.py       # Deep ticket context (7 parallel API calls)
|   |   |-- developer_skill.py       # Scope resolution + prompt building
|   |   |-- task_decomposer.py       # L/XL task decomposition into subtasks
|   |   |-- sentinel_integration.py  # Sentinel skill loading + stack detection
|   |   |-- pathfinder_parser.py     # Pathfinder comment parser
|   |   '-- repo_filter.py           # LLM-based repo filtering
|   |-- main.py              # Continuous loop mode
|   '-- run_once.py          # Single-scan mode
|-- Dockerfile
|-- docker-compose.yml
|-- entrypoint.sh
|-- requirements.txt         # python-dotenv, requests
'-- .env.example
```

---

## OpenClaw Integration

```bash
# Register as OpenClaw agent
openclaw agents add nightshift --workspace ~/NightShift --non-interactive

# Chat with NightShift
openclaw tui --session nightshift

# Run via agent command
openclaw agent --agent nightshift -m "scan for tickets" --timeout 3600

# Schedule hourly scans
openclaw cron add --name nightshift-scan --every 1h \
  --message "docker exec nightshift python3 engine/run_once.py" \
  --timeout 3600000
```

---

## Commands

| Command | What it does |
|---------|-------------|
| `scan` | Run the full pipeline |
| `status` | Show container logs |
| `check RUH-XXX` | Check specific ticket |
