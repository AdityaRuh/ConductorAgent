# TOOLS.md — Pathfinder Tooling

## Core Tools

### Linear Skill (`linear.sh`)
OpenClaw Linear skill for all Linear operations (from clawhub.ai/manuelhettich/linear).
Auth: Set `LINEAR_API_KEY` env var.

#### Personal Workflow
```bash
# Your Todo issues (key command for heartbeat)
linear.sh my-todos

# All issues assigned to you
linear.sh my-issues

# Urgent/high-priority items
linear.sh urgent

# Daily standup summary
linear.sh standup
```

#### Browse & Query
```bash
# List all teams
linear.sh teams

# Issues for a specific team
linear.sh team <KEY>

# All projects with progress
linear.sh projects

# Issues in a specific project
linear.sh project <name>
```

#### Issue Operations
```bash
# Detailed issue info
linear.sh issue <ID>

# Create a new issue
linear.sh create <TEAM_KEY> "Title" ["Description"]

# Add a comment to an issue
linear.sh comment <ID> "text"

# Generate a git branch name for an issue
linear.sh branch <ID>
```

#### Status Updates
```bash
# Update issue status
linear.sh status <ID> <todo|progress|review|done|blocked>

# Assign an issue
linear.sh assign <ID> <userName>

# Set priority
linear.sh priority <ID> <urgent|high|medium|low|none>
```

### GitHub CLI (`gh`)
For repo operations: cloning, reading code, checking PRs.
Already authenticated on machine.

### File System Tools
- `Read` — read files in repos
- `Grep` — search for code patterns
- `Glob` — find files by pattern
- `Bash` — run shell commands

## APIs
- Linear: via `linear.sh` skill
- GitHub: via `gh` CLI
