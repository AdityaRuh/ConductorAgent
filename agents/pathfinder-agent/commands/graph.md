---
description: Rebuild the Obsidian knowledge graph by scanning all connected repositories.
---

# /graph

Usage: `/graph [repo-name]`

## What it does
1. If `repo-name` specified, rebuilds only that repo's graph file
2. If no argument, rebuilds the entire knowledge graph:
   - Scans each repo in the portfolio
   - Reads project structure, configs, models, routes, gRPC defs
   - Updates `knowledge-graph/repos/*.md` files
   - Updates `knowledge-graph/connections/service-map.md`
3. Reports changes made

## Example
```
/graph

🧭 Pathfinder — Rebuilding knowledge graph...

Scanning agent-platform-v2...
  → Updated: 3 new key files, 1 new domain concept
Scanning agent-gateway...
  → No changes detected
Scanning communication-service...
  → Updated: 2 new gRPC methods found
Scanning ai-proxy...
  → Updated: new Kafka consumer added

Updating service-map.md...
  → 1 new connection: ai-proxy → communication-service via Kafka

🧭 Graph rebuild complete — 4 repos scanned, 3 updated
```

```
/graph ai-proxy

🧭 Pathfinder — Rebuilding graph for ai-proxy...

Scanning ai-proxy...
  → Overview: updated
  → Key files: 2 new files found
  → API surface: 1 new endpoint

🧭 Graph updated for ai-proxy
```
