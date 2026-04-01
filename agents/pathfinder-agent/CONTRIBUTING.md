# Contributing to Pathfinder

## Adding a New Skill

1. Create a directory under `skills/` with a `SKILL.md` file
2. Follow the existing pattern: frontmatter → Methodology → Steps → Verification Gates
3. Include at least 2 verification gates

## Adding a New Agent

1. Create a `.md` file in `agents/`
2. Include frontmatter: name, description, tools, model
3. Define: workflow, output format, critical rules

## Adding a New Command

1. Create a `.md` file in `commands/`
2. Include frontmatter with description
3. Define: what it does, example output

## Updating the Knowledge Graph

1. Repo files go in `knowledge-graph/repos/`
2. Follow existing repo file structure: Overview → Tech Stack → Architecture → Key Files → Domain Concepts → API Surface → Common Change Patterns → Connections
3. Update `knowledge-graph/connections/service-map.md` if connections change
4. Use `[[wikilinks]]` to cross-reference between notes
5. Always include `Last updated: YYYY-MM-DD`

## Adding a New Repo to the Portfolio

1. Create `knowledge-graph/repos/{repo-name}.md`
2. Update `knowledge-graph/connections/service-map.md`
3. Update the Connected Repositories table in `README.md`
4. Update domain area mapping in `skills/ticket-analysis/SKILL.md`
