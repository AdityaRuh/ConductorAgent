---
description: Generate a Technical Requirement Document for a specific feature issue.
---

# /trd

Usage: `/trd <issue-id>`

## What it does
1. Fetches the specified Linear issue via `linear.sh issue <ID>`
2. Skips classification — treats it as a feature
3. Spawns the TRD Agent
4. Identifies code changes via Repo Scanner
5. Posts TRD + code changes to the issue via `linear.sh comment <ID> "TRD content"`
6. Transitions to In Progress via `linear.sh status <ID> progress`

## Example
```
/trd RP-401

Pathfinder — TRD for RP-401

Feature: Add message reactions
Repos: agent-gateway, communication-service, proto-definitions
Complexity: M

TRD Highlights:
  - New REST endpoint: POST /conversations/{id}/messages/{id}/reactions
  - New gRPC method: AddReaction in CommunicationService
  - New field: reactions (List[Reaction]) on MessageModel
  - 6 acceptance criteria defined

TRD posted to RP-401
Transitioned to In Progress
```
