---
name: implementer
description: Implement fixes/features using TDD — make existing tests pass without editing them
---

# Implementer

Builds the Dev Agent prompt with Pathfinder RCA/TRD as primary context and TDD enforcement.

## Prompt Includes

1. **Dev Agent definition** (agents/dev-agent.md)
2. **Pathfinder analysis** — root cause, code changes table, fix approach
3. **Scope restrictions** — sub-task awareness, exclusions
4. **Ticket context** — description, acceptance criteria, comments, file hints
5. **TDD rules** — never edit tests, iterate until pass

## Scope Awareness

The implementer resolves ticket scope before building the prompt:

- Checks if ticket has a parent (sub-task detection)
- Checks if ticket has children with other assignees (scope exclusion)
- Inherits repo info from parent for sub-tasks without their own repo labels
- Builds exclusion list for other developers' sub-tasks

## Pathfinder Integration

When a Pathfinder comment exists:
- Code changes table injected as explicit instructions
- File hints merged from Pathfinder trace + ticket description
- Classification and complexity logged for tracking
