---
name: ticket-analysis
description: >
  Methodology for reading, understanding, and classifying Linear issues. Use this skill when
  processing a new issue from any Linear team. Covers: reading all issue fields, extracting
  context from linked issues and comments, classifying as bug vs feature, and identifying
  affected domain areas. Always load this skill before classifying any issue.
---

# Issue Analysis Skill

## Phase 1 — Fetch Issue Data

Retrieve all available information via `linear.sh issue <ID>`:

```
Fields to read:
- identifier (e.g., ABC-123)
- title
- description (markdown)
- state (Todo, In Progress, Done, Cancelled, etc.)
- priority (0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low)
- labels (array of label names — e.g., Bug, Feature, Improvement)
- assignee
- team
- project
- cycle (sprint equivalent)
- parent (parent issue)
- relations (blocked by, blocks, related, duplicate)
- comments (latest 10)
- attachments (names and types — look for logs, screenshots, specs)
```

## Phase 2 — Extract Context

Read beyond the surface:

### From the description:
- What is the user/system trying to do?
- What is the expected outcome?
- What is the actual outcome (for bugs)?
- Are there error messages or stack traces?
- Are there acceptance criteria?
- Are there technical details (endpoints, services, models mentioned)?

### From comments:
- Has the team discussed the approach?
- Are there clarifications from the reporter?
- Has anyone identified the root cause already?

### From linked issues (relations):
- Is this part of a larger initiative?
- Are there blocking dependencies?
- Have related bugs been fixed before?

### From the parent issue:
- What's the broader goal?
- What constraints does the parent set?

## Phase 3 — Classify

### Bug Signals (any 2+ = bug)
- Label is "Bug"
- Description contains error messages or stack traces
- Words present: "fix", "broken", "not working", "error", "fails", "crash", "regression", "wrong", "incorrect", "unexpected behavior"
- Linked to production incidents or hotfix branches
- Reporter describes "it used to work but now..."

### Feature Signals (any 2+ = feature)
- Label is "Feature", "Improvement", or no bug label
- Description contains requirements or acceptance criteria
- Words present: "add", "implement", "new", "support", "enable", "create", "build", "integrate", "enhance"
- Linked to product roadmap projects
- Contains UI/UX mockups or API specs

### Ambiguous Cases
- Single signal either way → read linked issues for more context
- Still ambiguous → **default to feature** (safer to over-plan than to under-diagnose)

## Phase 4 — Identify Domain Areas

Map the issue to domain areas in the codebase:

| Domain Area | Keywords | Repos Likely Affected |
|-------------|----------|----------------------|
| Agent execution | agent, tool, loop, prompt, chain | agent-platform-v2 |
| API gateway | endpoint, route, API key, rate limit, auth | agent-gateway |
| Conversations | conversation, message, chat, thread, history | communication-service |
| LLM/AI | model, inference, token, completion, stream | ai-proxy |
| Cross-cutting | all services, gRPC, proto, Kafka | multiple repos |

## Output

Produce the structured classification as defined in `agents/ticket-classifier.md`.
