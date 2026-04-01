# HEARTBEAT.md — Conductor Master Cycle

_Execute every 15 minutes. Each step must complete before the next begins._

---

## Phase 1: OBSERVE (read-only)

- [ ] **1.1 — Agent Health Check**
  Read `state/agents/` for all 5 agents. For each:
  - Parse `lastRunAt` and `lastSuccessAt` timestamps
  - Calculate time since last success
  - If `consecutiveFailures >= 3` or last success > 90 minutes ago → mark `unhealthy`
  - If any agent is `unhealthy` → create escalation in Phase 5

- [ ] **1.2 — Linear Pipeline Scan**
  Query Linear API for tickets across all configured teams (RP, SDR, RUH, TT):
  - `Todo` state → candidates for Pathfinder
  - `In Progress` state → Pathfinder completed, awaiting human approval
  - `Ready for Development` state → candidates for NightShift
  - `In Development` state → NightShift running or PR Resolver territory
  - `Code Review` state → review loop active or awaiting merge

- [ ] **1.3 — Active Task State Sync**
  For each file in `state/tasks/`:
  - Read the task JSON
  - Cross-reference with Linear ticket current state
  - If Linear state advanced beyond our tracked stage → update task state
  - If Linear ticket was closed/cancelled → mark task as `CANCELLED`, archive

- [ ] **1.4 — PR Status Check**
  For each task with `pr.number` set:
  - Check GitHub PR status (open/closed/merged)
  - Check latest review status (approved/changes_requested/pending)
  - Check CI pipeline status (pass/fail/running)
  - Update task state with findings

---

## Phase 2: DECIDE (logic, no side effects)

- [ ] **2.1 — New Ticket Intake**
  For each `Todo` ticket found in 1.2 that has NO entry in `state/tasks/`:
  - Create new task state file with `currentStage: "pathfinder"`, `status: "PENDING"`
  - Set budget based on complexity hint from ticket labels (default: M = 100,000 tokens)

- [ ] **2.2 — Stage Advancement**
  For each active task in `state/tasks/`:

  **If `currentStage == "pathfinder"` and `status == "SUCCESS"`:**
  - Verify plan comment exists on Linear ticket
  - Advance to waiting state (human must move to "Ready for Development")
  - Update: `currentStage: "awaiting-approval"`, `status: "BLOCKED"`

  **If `currentStage == "awaiting-approval"`:**
  - Check if Linear state is now `Ready for Development`
  - If yes → advance: `currentStage: "nightshift"`, `status: "PENDING"`

  **If `currentStage == "nightshift"` and `status == "SUCCESS"`:**
  - Verify PR exists on GitHub
  - Advance: `currentStage: "review-loop"`, `status: "PENDING"`, `reviewLoop.iteration: 0`

  **If `currentStage == "review-loop"`:**
  - Check PR review status:
    - If `approved` → advance: `currentStage: "pr-automation"`, `status: "PENDING"`
    - If `changes_requested` → check loop iteration count
      - If `iteration < 5` → set: `currentStage: "pr-resolver"`, `status: "PENDING"`, increment iteration
      - If `iteration >= 5` → set: `status: "BLOCKED"`, escalate
    - If `pending` (no review yet) → no action, PR Review Bot webhook will handle

  **If `currentStage == "pr-resolver"` and `status == "SUCCESS"`:**
  - PR Resolver pushed fixes → PR Review Bot will re-review via webhook
  - Return to: `currentStage: "review-loop"`, `status: "PENDING"`

  **If `currentStage == "pr-automation"` and `status == "SUCCESS"`:**
  - Release PR created → mark task `COMPLETED`

- [ ] **2.3 — Failure Handling**
  For each task with `status == "FAILED"`:
  - Read the failure details from task state
  - Classify failure type: transient / logical / dependency / budget / unknown
  - **Transient:** If `attempts < 3` → reset status to `PENDING` (will retry)
  - **Logical:** If `attempts < 2` → reset with adjusted context note
  - **Dependency:** Set `status: "BLOCKED"` with reason
  - **Budget / Unknown:** Set `status: "BLOCKED"`, prepare escalation

- [ ] **2.4 — Budget Check**
  For each active task:
  - Read `budget.spent` vs `budget.allocated`
  - If `spent > 0.8 * allocated` → add warning to escalation queue
  - If `spent >= allocated` → set `status: "BLOCKED"`, escalate

---

## Phase 3: ACT (trigger agents)

- [ ] **3.1 — Trigger Pathfinder**
  For tasks with `currentStage: "pathfinder"`, `status: "PENDING"`:
  - Pathfinder runs on its own 30-min heartbeat — Conductor only ensures the ticket is visible
  - Update task: `status: "RUNNING"`, `startedAt: now()`
  - Pathfinder's own heartbeat will pick it up

- [ ] **3.2 — Trigger NightShift**
  For tasks with `currentStage: "nightshift"`, `status: "PENDING"`:
  - NightShift runs on its own 60-min poll — Conductor ensures state is correct
  - If NightShift Docker container is not running → restart it
  - Update task: `status: "RUNNING"`, `startedAt: now()`

- [ ] **3.3 — Verify PR Review Bot**
  - Ensure PR Review Bot server is healthy: `curl http://localhost:8000/health`
  - If unhealthy → attempt restart, escalate if restart fails

- [ ] **3.4 — Trigger PR Resolver**
  For tasks with `currentStage: "pr-resolver"`, `status: "PENDING"`:
  - PR Resolver runs on its own 30-min heartbeat
  - Conductor ensures ticket is in `In Development` state for PR Resolver to find
  - Update task: `status: "RUNNING"`, `startedAt: now()`

- [ ] **3.5 — Trigger PR Automation**
  For tasks with `currentStage: "pr-automation"`, `status: "PENDING"`:
  - Run: `cd pr-automation/github-linear-automation && python main.py --target qa`
  - Update task: `status: "RUNNING"`, `startedAt: now()`

---

## Phase 4: RECORD (update state)

- [ ] **4.1 — Write Task States**
  Persist all task state changes from Phase 2 and Phase 3 to `state/tasks/`

- [ ] **4.2 — Update Agent Health**
  For each agent, update `state/agents/{agent}.json`:
  - `lastRunAt` from latest observed activity
  - Increment success/failure counters
  - Recalculate `averageLatencyMs`

- [ ] **4.3 — Update Metrics**
  Append to `state/metrics/daily.json`:
  - Tasks advanced, tasks failed, tasks completed
  - Total tokens consumed this cycle
  - Agent-level success/failure counts

---

## Phase 5: REPORT (communicate only if something changed)

- [ ] **5.1 — Escalations**
  For any BLOCKED task or unhealthy agent, send Telegram message:
  ```
  🎛️ Conductor Escalation

  Ticket: {TICKET-ID} — {title}
  Stage: {currentStage}
  Issue: {failure reason}
  Attempts: {count}
  Budget: {spent}/{allocated} tokens

  Action needed: {suggested human action}
  ```

- [ ] **5.2 — Cycle Summary** (only if tasks advanced or failed)
  Post to Telegram:
  ```
  🎛️ Conductor Cycle Summary

  Active tasks: {count}
  Advanced: {list of ticket IDs that moved forward}
  Blocked: {list of ticket IDs awaiting human}
  Completed: {list of ticket IDs finished this cycle}
  Agent health: {summary}
  ```

---

## Timing Rules

- Conductor heartbeat: **every 15 minutes**
- Pathfinder: runs independently every 30 minutes
- NightShift: runs independently every 60 minutes
- PR Review Bot: event-driven (webhook)
- PR Resolver: runs independently every 30 minutes
- Conductor does NOT re-run agents — it observes their output and manages routing
