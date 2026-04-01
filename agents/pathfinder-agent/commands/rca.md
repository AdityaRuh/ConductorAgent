---
description: Generate a Root Cause Analysis for a specific bug issue.
---

# /rca

Usage: `/rca <issue-id>`

## What it does
1. Fetches the specified Linear issue via `linear.sh issue <ID>`
2. Skips classification — treats it as a bug
3. Spawns the RCA Agent
4. Identifies code changes via Repo Scanner
5. Posts RCA + code changes to the issue via `linear.sh comment <ID> "RCA content"`
6. Transitions to In Progress via `linear.sh status <ID> progress`

## Example
```
/rca RP-400

Pathfinder — RCA for RP-400

Symptom: POST /conversations/{id}/messages returns 500 for conversations with >50 messages
Root Cause: Missing compound index on (conversation_id, created_at) in communication-service
Fix: Add index to MessageModel, verify query uses it

Affected Files:
  communication-service:
    app/models/message_model.py — Add compound index
    tests/test_message_service.py — Add pagination test

RCA posted to RP-400
Transitioned to In Progress
```
