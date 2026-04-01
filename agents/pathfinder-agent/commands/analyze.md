---
description: Analyze a specific Linear issue — classify, generate RCA/TRD, identify code changes, post plan.
---

# /analyze

Usage: `/analyze <issue-id>`

## What it does
1. Fetches the specified Linear issue via `linear.sh issue <ID>`
2. Runs the full Pathfinder pipeline on it:
   - Classify (bug/feature)
   - Generate RCA or TRD
   - Identify code changes
   - Assemble plan
   - Post to Linear via `linear.sh comment <ID> "plan content"`
   - Transition to In Progress via `linear.sh status <ID> progress`
3. Reports the result

## Example
```
/analyze RP-365

Pathfinder — Analyzing RP-365...

Issue: "Issue Intake & Analysis — RCA, TRDs, subtask generation, knowledge graph"
Classification: feature
Priority: Medium

Generating TRD...
  → Scope: Pre-coding automation agent
  → Affected repos: None (new project)
  → Complexity: XL

TRD posted to RP-365
Transitioned to In Progress
```
