# Knowledge Graph

This is Pathfinder's Obsidian vault — the map of all Ruh AI repositories, their architecture, and how they connect.

## Structure

```
knowledge-graph/
├── repos/                  One file per repository
│   ├── agent-platform-v2.md
│   ├── agent-gateway.md
│   ├── communication-service.md
│   └── ai-proxy.md
├── connections/            Inter-service relationships
│   └── service-map.md
└── README.md               This file
```

## How to Use

1. **Finding which repo owns a feature:** Read the "Domain Concepts" section in each repo file
2. **Understanding a request flow:** Read `connections/service-map.md`
3. **Finding key files:** Read the "Key Files" section in the repo file
4. **Checking cross-repo impacts:** Read the "Connections" section in service-map.md

## Maintenance

- Run `/graph` to auto-rebuild from current repo state
- Run `/graph <repo>` to refresh a single repo
- Always check `Last updated` dates — stale entries can mislead

## Obsidian Links

Files use `[[wikilinks]]` to cross-reference. Open this directory as an Obsidian vault to see the graph visualization.
