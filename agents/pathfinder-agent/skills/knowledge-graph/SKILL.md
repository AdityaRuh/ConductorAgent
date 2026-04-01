---
name: knowledge-graph
description: >
  How to use and maintain the Obsidian knowledge graph. Use this skill when consulting
  the knowledge graph for repo information, service connections, or when updating the graph
  with new findings. The knowledge graph is Pathfinder's map of the codebase landscape.
---

# Knowledge Graph Skill

## What the Graph Contains

The knowledge graph is an Obsidian vault at `knowledge-graph/` with:

### Repo Files (`knowledge-graph/repos/`)
One file per repository, containing:
- **Overview** — what the service does in 2-3 sentences
- **Tech Stack** — language, framework, DB, key dependencies
- **Architecture** — layers (router → service → repo → model)
- **Key Files** — the most important files and what they do
- **API Surface** — REST endpoints, gRPC methods, Kafka topics
- **Domain Concepts** — what domain objects this service owns
- **Common Change Patterns** — "when X changes, usually modify Y"

### Connection Files (`knowledge-graph/connections/`)
- **service-map.md** — how services talk to each other
  - gRPC connections (who calls whom)
  - Kafka flows (who produces, who consumes)
  - Shared dependencies (proto-definitions, shared models)
  - Request flow diagrams

## How to Read the Graph

### For ticket analysis:
1. Identify domain areas from the ticket (e.g., "conversations", "agents", "auth")
2. Read repo files to find which repos own that domain
3. Read service-map.md to find cross-repo flows

### For code change detection:
1. Read the repo file for key files and architecture
2. Use the "Common Change Patterns" section to find related files
3. Read service-map.md to find downstream impacts

### For RCA:
1. Read the repo file for the service where the bug manifests
2. Trace through service-map.md to find upstream causes
3. Use key files to quickly navigate to the right code

## How to Update the Graph

Update the graph when you discover:
- New files or modules not in the graph
- Changed architecture (renamed files, new layers)
- New API endpoints or gRPC methods
- New Kafka topics
- New inter-service connections
- Changed domain ownership

### Update rules:
- Keep entries factual and current — no opinions
- Include file paths that can be verified
- Use Obsidian `[[wikilinks]]` to link between notes
- Date your updates with a `Last updated: YYYY-MM-DD` line

## Graph Maintenance

The graph should be refreshed when:
- A new repo is added to the portfolio
- After a major refactor in any repo
- When Pathfinder encounters a file not in the graph
- On `/graph` command (manual rebuild)

Staleness is the enemy. A wrong graph is worse than no graph.
