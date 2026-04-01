# AGENTS.md — NightShift Sub-Agents

## Agent Portfolio

| Agent | File | Purpose | Model |
|-------|------|---------|-------|
| **Test Agent** | `agents/test-agent.md` | Generates comprehensive test suites using Sentinel Guardian methodology | sonnet |
| **Dev Agent** | `agents/dev-agent.md` | Implements fixes using TDD — makes tests pass without editing them | sonnet |

## Execution Order

For each ticket, per repo:

```
1. Test Agent  →  writes tests  →  commits: test(TICKET-ID): add tests
2. Dev Agent   →  implements    →  commits: fix(TICKET-ID): description
```

Both agents are invoked as Claude Code CLI sessions with carefully constructed prompts. Each agent runs in an isolated git worktree.

## Agent Interaction

- Test Agent writes test files and commits them
- Dev Agent reads those test files and implements code to make them pass
- There is NO direct communication between agents — they share state via the git worktree (committed files)
- If Test Agent's session removes the worktree, NightShift recreates it from the branch before starting Dev Agent
