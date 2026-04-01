---
name: test-generator
description: Generate comprehensive test suites using Sentinel Guardian methodology, adapted to repo stack
---

# Test Generator

Loads Sentinel Guardian testing skills and builds a comprehensive test prompt for the Test Agent.

## Stack Detection

Automatically detects the repo's tech stack:

| Stack | Signal Files | Test Skills Used |
|-------|-------------|-----------------|
| Backend | requirements.txt, go.mod, Cargo.toml, etc. | test-setup, unit, integration, contract, security, resilience, smoke, e2e-api, test-review |
| Frontend | next.config.*, React/Vue in package.json | test-setup, unit, e2e-browser, test-review |
| Full-stack | Both signals present | All skills |

## How It Works

1. Detects stack from worktree files
2. Loads ALL relevant Sentinel SKILL.md files
3. Loads the test-agent.md definition
4. Combines with ticket context (description, acceptance criteria, Pathfinder analysis)
5. Produces a single comprehensive prompt for one Claude Code session

## Key Principle

All test layers are generated in ONE Claude Code session. Claude sequences them internally (unit first, then integration, then security, etc.) — no need for separate sessions per skill.
