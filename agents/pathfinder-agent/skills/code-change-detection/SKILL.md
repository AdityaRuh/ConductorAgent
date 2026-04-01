---
name: code-change-detection
description: >
  Methodology for identifying exact code change locations in repositories. Use this skill
  when you need to map requirements or bug fixes to specific files, functions, and classes.
  Covers: knowledge graph consultation, repo scanning, call chain tracing, cross-repo
  impact detection. Always load this skill before scanning repos for code changes.
---

# Code Change Detection Skill

## Methodology: Graph → Scan → Trace → Verify

### Step 1 — Consult the Knowledge Graph

Before touching any repo, read:
1. `knowledge-graph/repos/{repo}.md` for each potentially affected repo
2. `knowledge-graph/connections/service-map.md` for inter-service flows

From the graph, build an initial hypothesis:
- Which repos own the affected domain?
- What are the key entry points (routers, gRPC handlers, Kafka consumers)?
- What are the key service classes?
- What models/schemas are involved?

### Step 2 — Scan the Repo

For each affected repo, use targeted searches:

```bash
# Find files related to a domain area
Glob: app/**/*conversation*.py
Glob: app/**/*message*.py

# Find functions/classes
Grep: "class ConversationService"
Grep: "def create_conversation"
Grep: "async def handle_message"

# Find route definitions
Grep: "@router\.(get|post|put|delete|patch)"
Grep: "rpc.*Method"

# Find Kafka handlers
Grep: "consume|producer|kafka"

# Find model definitions
Grep: "class.*Model.*Document"
Grep: "class.*Schema.*BaseModel"
```

### Step 3 — Trace the Call Chain

Starting from the entry point, follow the call chain:

```
Router/Handler (entry point)
    → Service method (business logic)
        → Repository/Client (data access)
            → Model/Schema (data shape)
```

For each step:
1. Read the function signature
2. Read what it calls
3. Identify what needs to change
4. Note the import chain (what breaks if this file changes)

### Step 4 — Identify All Change Points

Categorize changes:

**Direct changes** (the code that implements the requirement):
- New or modified functions
- New or modified models
- New or modified routes

**Supporting changes** (needed for direct changes to work):
- Import updates
- Config/env additions
- Proto file updates + regeneration
- Kafka topic registration
- Dependency additions (pyproject.toml, package.json)

**Test changes** (verification of the above):
- New test files
- Modified test fixtures
- Updated mocks

### Step 5 — Verify and Cross-Check

Before finalizing:
- [ ] Every listed file exists (verified via Glob/Read)
- [ ] Every listed function exists (verified via Grep/Read)
- [ ] No orphaned changes (if A changes, everything that imports A is checked)
- [ ] Proto changes propagated to all consuming services
- [ ] Kafka topic changes reflected in all producers and consumers
- [ ] Config changes listed for all affected deployments

## Common Cross-Repo Patterns

| Change Type | Repos Affected |
|-------------|---------------|
| gRPC proto change | proto-definitions → all services that import the proto |
| New Kafka topic | Producer service + consumer service + topic config |
| Auth change | agent-gateway (API auth) + any service with direct auth |
| New model field | Service that owns the model + all services that query it |
| New environment variable | Service code + Kubernetes config + CI/CD |

## Anti-Patterns to Avoid

- **Listing a file without verifying it exists** — repos change, the graph may be stale
- **Missing test files** — if you change `app/services/foo.py`, check `tests/test_foo.py`
- **Ignoring proto-definitions** — gRPC changes always start in the proto repo
- **Forgetting config** — new features almost always need new env vars
- **Single-repo thinking** — most features touch 2+ repos in a microservice architecture
