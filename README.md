# Conductor Agent

Central orchestration layer for the Ruh AI autonomous SDLC pipeline. Conductor coordinates five specialized agents that turn a Linear ticket into merged, production-ready code — with zero human intervention in the happy path.

---

## Pipeline Overview

```
LINEAR TICKET (Todo)
        │
        ▼
┌───────────────────────────────────┐
│  [1] PATHFINDER 🧭                │
│  Pre-coding analysis agent        │
│  Classifies Bug/Feature           │
│  Posts RCA or TRD plan            │
│  Ticket → In Progress             │
└───────────────┬───────────────────┘
                │
                ▼
┌───────────────────────────────────┐
│  [2] NIGHTSHIFT 🌙                │
│  Autonomous dev agent             │
│  Writes tests (TDD) → Implements │
│  Opens PR on GitHub               │
│  Ticket → Code Review             │
└───────────────┬───────────────────┘
                │
                ▼
┌───────────────────────────────────┐
│  [3] PR REVIEW BOT 🔍             │
│  AI-powered PR reviewer           │
│  Posts inline review comments     │
│  Clean → Ready to Deploy          │
│  Issues → Require Changes         │
└───────────────┬───────────────────┘
                │
                │  ◄──────────────────────────┐
                ▼                              │
┌───────────────────────────────────┐          │
│  [4] PR RESOLVER 🔧               │   LOOP   │
│  Reads review comments            │   until  │
│  Classifies intent (7-tier)       │   PR     │
│  Fixes code → Runs CI             │   Review │
│  Ticket → Code Review             │   Bot    │
└───────────────┬───────────────────┘  APPROVES│
                │                              │
                └── Still has changes? ────────┘
                │
                ▼  (Approved)
┌───────────────────────────────────┐
│  [5] PR AUTOMATION 🚀             │
│  Cherry-picks into release branch │
│  Creates QA/Prod release PRs      │
│  Ticket → Released to Prod        │
└───────────────┬───────────────────┘
                │
                ▼
          CODE MERGED ✓
```

---

## What Conductor Does

Conductor is the meta-agent — it does not write code, open PRs, or modify Linear tickets. It **observes, routes, decides, recovers, and escalates.**

Every **15 minutes**, it executes a 5-phase heartbeat cycle:

| Phase | Name | What It Does |
|-------|------|-------------|
| 1 | **OBSERVE** | Scans Linear for tickets across all pipeline states. Checks agent health. Syncs task state files with Linear reality. Checks PR/CI status on GitHub. |
| 2 | **DECIDE** | Intakes new tickets. Advances tasks through stages. Classifies failures. Manages the Review Bot ↔ Resolver loop. Enforces budgets. |
| 3 | **ACT** | Ensures agents are running (Docker health, webhook health). Marks tasks as RUNNING. Triggers PR Automation on-demand. |
| 4 | **RECORD** | Persists all state changes. Updates agent health records. Appends daily metrics. |
| 5 | **REPORT** | Sends Telegram escalations for blocked tasks. Posts cycle summary if anything changed. |

---

## Architecture

```
                     ┌──────────────────────────────────┐
                     │       CONDUCTOR 🎛️                │
                     │    Heartbeat: every 15 min        │
                     │                                   │
                     │  Reads: Linear + GitHub + State   │
                     │  Decides: routing + recovery      │
                     │  Tracks: health + budget + metrics│
                     │  Escalates: Telegram              │
                     └───┬──────┬──────┬──────┬──────┬──┘
                         │      │      │      │      │
           ┌─────────────┘      │      │      │      └─────────────┐
           ▼                    ▼      │      ▼                    ▼
    ┌─────────────┐   ┌─────────────┐  │  ┌─────────────┐  ┌──────────────┐
    │ PATHFINDER   │   │ NIGHTSHIFT  │  │  │ PR RESOLVER │  │ PR AUTOMATION│
    │ 30min cycle  │   │ 60min cycle │  │  │ 30min cycle │  │ on-demand    │
    │ OpenClaw     │   │ Python/     │  │  │ Bash/       │  │ Python CLI   │
    │ agent        │   │ Docker      │  │  │ OpenClaw    │  │              │
    └─────────────┘   └─────────────┘  │  └─────────────┘  └──────────────┘
                                       │
                              ┌────────────────┐
                              │ PR REVIEW BOT  │
                              │ FastAPI webhook│
                              │ event-driven   │
                              └────────────────┘
```

---

## Agent Details

### 1. Pathfinder 🧭 — Pre-Coding Analyst

| | |
|---|---|
| **Location** | `agents/pathfinder-agent/` |
| **Trigger** | Heartbeat every 30 minutes |
| **Watches** | Linear tickets in `Todo` state |
| **Does** | Classifies ticket as Bug or Feature. For bugs: generates Root Cause Analysis (RCA). For features: generates Technical Requirements Document (TRD). Maps exact files/functions to change using knowledge graph. Posts plan as Linear comment. |
| **Transitions** | `Todo` → `In Progress` |
| **Sub-agents** | ticket-classifier, rca-agent, trd-agent, repo-scanner, plan-writer |

### 2. NightShift 🌙 — Autonomous Developer

| | |
|---|---|
| **Location** | `agents/NightShift/` |
| **Trigger** | Python poll every 60 minutes (Docker) |
| **Watches** | Linear tickets in `Ready for Development` state |
| **Requires** | Pathfinder plan comment on ticket |
| **Does** | Clones repos. Runs Test Agent (writes tests using Sentinel Guardian methodology). Runs Dev Agent (implements code to make tests pass — TDD). Pushes branch. Creates PR. Posts PR link to Linear. |
| **Transitions** | `Ready for Development` → `In Development` → `Code Review` |
| **Sub-agents** | test-agent, dev-agent |

### 3. PR Review Bot 🔍 — AI Reviewer

| | |
|---|---|
| **Location** | `agents/pr-review-bot/` |
| **Trigger** | GitHub webhook (`pull_request`: opened, synchronize, reopened) |
| **Does** | Dispatches PR to Sentinel reviewer via OpenClaw. Polls for review comment. Parses findings (P1/P2/P3 severity). Transitions Linear ticket based on findings. Notifies PR author via Slack DM. |
| **Transitions** | Issues found → `Require Changes` (fallback: `In Development`). Clean → `Ready to Deploy - Dev` (fallback: `Ready to Deploy`). |
| **Debounce** | 30 seconds (avoids duplicate reviews on rapid pushes) |

### 4. PR Resolver 🔧 — Review Comment Resolver

| | |
|---|---|
| **Location** | `agents/pr-resolver/` |
| **Trigger** | Heartbeat every 30 minutes |
| **Watches** | Linear tickets in `Require Changes` state |
| **Does** | Fetches all PR review comments. Deduplicates (SHA-256). Classifies intent with 7-tier system (regex + LLM). Routes: skip bots/approvals, flag subjective to Telegram, answer questions, fix code changes. For fixes: explores codebase → plans → implements → independent reviewer validates (up to 3 cycles) → runs tests → commits → pushes → watches CI (up to 5 repair attempts). |
| **Transitions** | `Require Changes` → `Code Review` (when all resolved + CI green) |
| **Budget** | Max 3 fixes/PR/cycle, 10/cycle, 20/hour |

### 5. PR Automation 🚀 — Release Manager

| | |
|---|---|
| **Location** | `agents/pr-automation/` |
| **Trigger** | On-demand (manual or Conductor-initiated) |
| **Watches** | `Ready to Deploy - QA` or `Approved for Prod` |
| **Does** | Queries Linear for target tickets. Scans repos for matching commits. Cherry-picks onto release branch. Auto-resolves conflicts with Claude CLI. Creates release PRs with ticket summaries. |
| **Transitions** | `Ready to Deploy - QA` → `In QA`. `Approved for Prod` → `Released to Prod`. |

---

## Linear State Machine

```
Todo                          ← Pathfinder watches
  │
  ▼
In Progress                   ← Plan posted, human reviews
  │
  ▼
Ready for Development         ← Human approved, NightShift watches
  │
  ▼
In Development                ← Code being written
  │
  ▼
Code Review                   ← PR exists, PR Review Bot reviews
  │
  ├── Clean review ──────────► Ready to Deploy - QA
  │                                    │
  └── Issues found ──► Require Changes │
                            │          │
                      PR Resolver      │
                      fixes code       │
                            │          │
                       Code Review ◄───┘
                            │
                            ▼
                      In QA
                            │
                            ▼
                      Approved for Prod
                            │
                            ▼
                      Released to Prod ✓
```

---

## Failure Classification

Conductor classifies every failure before deciding what to do:

| Type | Signals | Action | Max Retries |
|------|---------|--------|-------------|
| **Transient** | HTTP 429, 502, timeout, rate limit | Retry with exponential backoff | 3 |
| **Logical** | Malformed output, wrong classification | Re-run with adjusted context | 2 |
| **Dependency** | Upstream not complete, missing data | Wait for next heartbeat | 0 |
| **Budget** | Token limit reached | Block + escalate to human | 0 |
| **Health** | Container down, server unreachable | Attempt restart, then escalate | 1 |
| **Unknown** | Unrecognized error | Escalate immediately | 0 |

---

## Budget Management

Each task gets a token budget based on complexity:

| Complexity | Total Budget | Pathfinder | NightShift | Review Loop | PR Automation |
|-----------|-------------|-----------|-----------|------------|--------------|
| S | 50,000 | 5,000 | 25,000 | 15,000 | 5,000 |
| M | 100,000 | 10,000 | 50,000 | 30,000 | 10,000 |
| L | 200,000 | 15,000 | 100,000 | 65,000 | 20,000 |
| XL | 400,000 | 25,000 | 200,000 | 130,000 | 45,000 |

**Thresholds:** 60% → log. 80% → Telegram warning. 90% → restrict to essential ops. 100% → block + escalate.

---

## Human Escalation

Conductor escalates to Telegram when autonomous resolution is insufficient:

**Always escalate:**
- Unknown failure
- Budget exhausted
- Agent unhealthy for 3+ cycles
- Review loop hit 5 iterations
- CI failed 3 times after fixes
- Subjective/design-level reviewer feedback
- Security-sensitive file modified

**Human can respond with:**
- `retry` — reset task, clear failures
- `skip` — advance past current stage
- `cancel` — abandon task
- `increase budget` — raise token limit
- `ignore` — keep blocked, suppress re-escalation

---

## Agent Health Monitoring

| Condition | Status | Action |
|-----------|--------|--------|
| Last success < 1 cycle ago | `healthy` | No action |
| Last success 1-2 cycles ago | `degraded` | Log warning |
| Last success 3+ cycles ago | `unhealthy` | Escalate to Telegram |
| Consecutive failures >= 3 | `critical` | Escalate + pause routing |

---

## Project Structure

```
.
├── SOUL.md                          # Conductor philosophy and principles
├── IDENTITY.md                      # Agent identity
├── ARCHITECTURE.md                  # Full system topology and schemas
├── AGENTS.md                        # Registry of all 5 sub-agents
├── TOOLS.md                         # Available tools and usage rules
├── HEARTBEAT.md                     # 15-min master cycle (5 phases)
├── docker-compose.yml               # Master compose for all 5 agents
├── .env.example                     # All environment variables
│
├── agents/
│   ├── pathfinder-agent/            # [1] Pre-coding analyst
│   │   ├── SOUL.md
│   │   ├── HEARTBEAT.md
│   │   ├── agents/                  # Sub-agent definitions
│   │   ├── skills/                  # Analysis skills
│   │   ├── knowledge-graph/         # Repo architecture index
│   │   ├── templates/               # RCA/TRD output templates
│   │   ├── Dockerfile
│   │   └── entrypoint.sh
│   │
│   ├── NightShift/                  # [2] Autonomous dev agent
│   │   ├── SOUL.md
│   │   ├── engine/                  # Python orchestration engine
│   │   │   ├── main.py              # Continuous poll mode
│   │   │   ├── run_once.py          # Single scan mode
│   │   │   └── lib/
│   │   │       ├── core.py          # 3-phase pipeline
│   │   │       ├── linear_client.py # Linear GraphQL client
│   │   │       └── config.py
│   │   ├── skills/                  # Dev skills
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   └── entrypoint.sh
│   │
│   ├── pr-review-bot/               # [3] Webhook PR reviewer
│   │   ├── app/
│   │   │   ├── main.py              # FastAPI webhook handler
│   │   │   ├── config.py
│   │   │   ├── linear_client.py
│   │   │   ├── slack_notifier.py
│   │   │   └── github_client.py
│   │   ├── review_rules/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── pr-resolver/                 # [4] Review comment resolver
│   │   ├── SOUL.md                  # 21-step workflow
│   │   ├── AGENTS.md                # 30 micro-agents
│   │   ├── lib/
│   │   │   ├── pr-resolver.sh       # Main orchestrator (1700+ lines)
│   │   │   └── linear.sh            # Linear API integration
│   │   ├── skills/
│   │   ├── Dockerfile
│   │   └── entrypoint.sh
│   │
│   └── pr-automation/               # [5] Release automation
│       ├── github-linear-automation/
│       │   ├── main.py              # CLI entry point
│       │   ├── config/boards.yaml   # Team/release config
│       │   └── core/
│       │       ├── cherry_pick.py
│       │       ├── commit_scanner.py
│       │       ├── github_client.py
│       │       ├── linear_client.py
│       │       └── release_manager.py
│       ├── Dockerfile
│       └── entrypoint.sh
│
├── dashboard/                       # [6] Mission Control — operations dashboard
│   ├── src/                         # Next.js app (pages, API routes, components)
│   ├── public/                      # Static assets
│   ├── Dockerfile                   # Multi-stage build (standalone output)
│   ├── docker-entrypoint.sh
│   ├── .env.local                   # Local dashboard config
│   └── .data/                       # SQLite DB + session data (gitignored)
│
├── skills/                          # Conductor-specific skills
│   ├── task-routing/SKILL.md        # Linear state → agent routing
│   ├── failure-classification/SKILL.md
│   ├── human-escalation/SKILL.md
│   ├── cost-tracking/SKILL.md       # Token budgets
│   ├── linear/SKILL.md              # Linear API patterns
│   └── github/SKILL.md              # PR/CI monitoring
│
├── state/                           # Persistent state (source of truth)
│   ├── tasks/                       # Per-ticket lifecycle (JSON)
│   ├── agents/                      # Per-agent health records
│   │   ├── pathfinder.json
│   │   ├── nightshift.json
│   │   ├── pr-review-bot.json
│   │   ├── pr-resolver.json
│   │   └── pr-automation.json
│   ├── metrics/
│   │   ├── daily.json               # Aggregated daily metrics
│   │   └── history/                 # Rolling 30-day
│   └── budget/                      # Per-ticket token usage
│
└── templates/
    └── task-state.template.json     # Template for new task state
```

---

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Fill in all values — at minimum:
#   LINEAR_API_KEY
#   GH_TOKEN
#   CLAUDE_CODE_OAUTH_TOKEN
#   TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
```

### 2. Start All Agents (Docker)

```bash
# Start the 4 continuous agents
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f pathfinder
docker compose logs -f nightshift
docker compose logs -f pr-review-bot
docker compose logs -f pr-resolver
```

### 3. Run PR Automation (On-Demand)

```bash
# QA release
docker compose run --rm pr-automation

# Prod release
docker compose run --rm -e RELEASE_TARGET=prod pr-automation
```

### 4. Start Conductor (OpenClaw)

Conductor runs as an OpenClaw agent with a 15-minute heartbeat. Add to `~/.openclaw/openclaw.json`:

```json
{
  "agents": {
    "list": [
      {
        "id": "conductor",
        "workspace": "/path/to/this/repo",
        "heartbeat": {
          "every": "15m",
          "target": "last",
          "isolatedSession": false,
          "lightContext": false,
          "prompt": "Read HEARTBEAT.md and execute the full 5-phase cycle: OBSERVE → DECIDE → ACT → RECORD → REPORT."
        }
      }
    ]
  }
}
```

Then restart the gateway:

```bash
openclaw gateway restart
```

### 5. Smoke Test

```bash
openclaw agent --workspace . --local -p "Execute Phase 1 OBSERVE only. Check Linear API, GitHub auth, all agent health files. Report a summary table with PASS/FAIL per component."
```

---

## Mission Control Dashboard

Mission Control is the operations dashboard for monitoring and managing all agents in the pipeline. Built with Next.js and backed by SQLite.

```
http://localhost:3000
Login: admin / ConductorAdmin2026!
```

### What You Can See

| Panel | Description |
|-------|-------------|
| **Fleet Overview** | All 6 agents with live status (healthy/degraded/offline) |
| **Agents** | Individual agent details, last heartbeat, uptime, error count |
| **Tasks** | Active task queue with Linear ticket mapping and pipeline stage |
| **Activity Feed** | Real-time log of agent actions, state transitions, escalations |
| **Chat** | Send commands to agents via the OpenClaw gateway |
| **Memory** | Browse agent memory and knowledge graph |
| **Cron** | View and manage agent heartbeat schedules |
| **Webhooks** | Monitor incoming GitHub webhook events |
| **Alerts** | Escalation history and unresolved warnings |
| **Security Audit** | Agent permission usage and tool call logs |
| **Cost Tracking** | Token usage per agent and per task |
| **Settings** | Gateway config, agent registration, credentials |

### Access

Mission Control starts automatically with `docker compose up -d` on port **3000**.

To run standalone (without Docker):

```bash
cd dashboard
pnpm install
pnpm build
pnpm start
```

### Configuration

Set these in `.env` (see `.env.example` for all options):

| Variable | Default | Description |
|----------|---------|-------------|
| `MC_PORT` | `3000` | Dashboard port |
| `MC_AUTH_USER` | `admin` | Login username |
| `MC_AUTH_PASS` | `changeme` | Login password |
| `OPENCLAW_GATEWAY_HOST` | `127.0.0.1` | OpenClaw gateway host (server-side) |
| `OPENCLAW_GATEWAY_PORT` | `18789` | OpenClaw gateway port |
| `NEXT_PUBLIC_GATEWAY_HOST` | `127.0.0.1` | Gateway host (browser-side) |
| `NEXT_PUBLIC_GATEWAY_PORT` | `18789` | Gateway port (browser-side) |
| `NEXT_PUBLIC_GATEWAY_PROTOCOL` | `ws` | `ws` for local, `wss` for production (secure WebSocket) |
| `OPENCLAW_HOME` | `~/.openclaw` | Where agent state, metrics, and config live |

---

## Docker Commands

| Command | Description |
|---------|------------|
| `docker compose up -d` | Start all 5 services (4 agents + dashboard) |
| `docker compose ps` | Check running containers |
| `docker compose logs -f <service>` | Follow logs for one service |
| `docker compose restart <service>` | Restart a specific service |
| `docker compose down` | Stop all services |
| `docker compose run --rm pr-automation` | Run QA release (on-demand) |
| `docker compose run --rm -e RELEASE_TARGET=prod pr-automation` | Run Prod release |

---

## Environment Variables

| Variable | Used By | Required |
|----------|---------|----------|
| `LINEAR_API_KEY` | All agents | Yes |
| `GH_TOKEN` | NightShift, PR Resolver, PR Automation | Yes |
| `CLAUDE_CODE_OAUTH_TOKEN` | Pathfinder, NightShift, PR Resolver | Yes |
| `TELEGRAM_BOT_TOKEN` | Conductor, PR Resolver | Yes |
| `TELEGRAM_CHAT_ID` | Conductor, PR Resolver | Yes |
| `SLACK_BOT_TOKEN` | PR Review Bot | Optional |
| `GITHUB_PAT` | PR Review Bot | Yes |
| `WEBHOOK_SECRET` | PR Review Bot | Yes |
| `GITHUB_ORG` | NightShift, PR Automation | Default: `ruh-ai` |
| `TARGET_BRANCH` | NightShift | Default: `dev` |
| `SSH_KEY_PATH` | NightShift, PR Resolver | Default: `~/.ssh/id_ed25519` |
| `SENTINEL_SKILLS_PATH` | NightShift | Default: `~/.openclaw/workspace/sentinel-guardian/skills` |
| `BOT_GITHUB_USER` | PR Resolver | Default: `AdityaRuh` |
| `LINEAR_ASSIGNEE_EMAIL` | PR Resolver | Yes |
| `MC_PORT` | Mission Control | Default: `3000` |
| `MC_AUTH_USER` | Mission Control | Default: `admin` |
| `MC_AUTH_PASS` | Mission Control | Yes |
| `OPENCLAW_GATEWAY_PORT` | Mission Control | Default: `18789` |
| `OPENCLAW_HOME` | Mission Control | Default: `~/.openclaw` |

---

## Security

- All secrets via environment variables — never in state files or code
- Each agent runs in an isolated Docker container
- Git operations scoped to specific branches — never force-push to main/dev
- CLI commands restricted via OpenClaw `gateway.nodes.denyCommands`
- State files maintain append-only audit trail
- Conductor has read-only access to Linear and GitHub — agents perform mutations
- Single `.env` file at root, symlinked to all agents

---

## Monitored Repositories

- `ruh-ai/strapi-service`
- `ruh-ai/hubspot-mcp`
- `ruh-ai/salesforce-mcp`
- `ruh-ai/sdr-backend`
- `ruh-ai/inbox-rotation-service`
- `ruh-ai/sdr-management-mcp`
- `ruh-ai/ruh-app-fe`
- `ruh-ai/agent-platform-v2`
- `ruh-ai/agent-gateway`
- `ruh-ai/communication-service`
- `ruh-ai/ai-proxy`

---

## Team

| Agent | Creator |
|-------|---------|
| Pathfinder | Akshit Gupta (@akshiitGpt) |
| NightShift | Rishabh Kala (@Rishabh-Kala-ruh) |
| PR Review Bot | Shivam Rajput (@shivam-ruh) |
| PR Resolver | Aditya (@AdityaRuh) |
| PR Automation | Ruh AI (@ruh-ai) |
| Conductor | Ruh AI Engineering |

---

## Built With

- [OpenClaw](https://openclaw.ai) — Agent runtime and gateway
- [Claude](https://anthropic.com) — LLM backbone (Sonnet 4.6)
- [Linear](https://linear.app) — Project management and state machine
- [GitHub](https://github.com) — Code hosting, PRs, CI/CD
- [Telegram](https://telegram.org) — Human escalation channel
- [Docker](https://docker.com) — Agent isolation and deployment
- [Mission Control](https://github.com/builderz-labs/mission-control) — Operations dashboard
