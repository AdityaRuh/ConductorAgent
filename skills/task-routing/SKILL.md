---
name: task-routing
description: Route Linear tickets through the 5-stage pipeline based on current state
---

# Task Routing

Determines which agent should handle a ticket based on its current Linear state and task state file.

## Routing Table

| Linear State | Task File Stage | Route To |
|-------------|-----------------|----------|
| `Todo` (no task file) | N/A | Create task → Pathfinder |
| `Todo` (task exists) | `pathfinder` RUNNING | Wait — Pathfinder is working |
| `In Progress` | `pathfinder` SUCCESS | `awaiting-approval` — human must approve plan |
| `Ready for Development` | `awaiting-approval` | NightShift |
| `In Development` (no PR) | `nightshift` RUNNING | Wait — NightShift is working |
| `In Development` (PR exists) | `nightshift` SUCCESS | Review Loop |
| `Code Review` | `review-loop` | Check PR review status |
| `Code Review` (changes requested) | `review-loop` | PR Resolver |
| `Code Review` (approved) | `review-loop` | PR Automation |
| `Ready to Deploy - QA` | `pr-automation` PENDING | PR Automation (QA target) |
| `Approved for Prod` | `pr-automation` PENDING | PR Automation (Prod target) |

## Conflict Resolution

If Linear state and task state disagree:
1. Trust Linear state as the authority for ticket status
2. Trust task state for internal tracking (attempts, budget, loop count)
3. If Linear moved forward unexpectedly → sync task state forward
4. If Linear moved backward → flag as anomaly, escalate

## Priority Assignment

Tasks inherit priority from Linear ticket:
- `Urgent` → process immediately, skip queue
- `High` → next in queue
- `Medium` → standard queue
- `Low` → process after all higher priorities
- Within same priority → FIFO by `createdAt`
