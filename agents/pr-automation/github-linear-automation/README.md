# GitHub-Linear Automation 🍒

Automates release workflows by syncing Linear tickets to GitHub PRs.

## What It Does

1. Queries Linear for tickets in target status (Ready to Deploy, Approved for Prod)
2. Scans GitHub repos for commits referencing those ticket IDs
3. Cherry-picks commits onto release branches
4. Opens PRs with full ticket context

## Quick Start

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure .env
cp .env.example .env
# Add your LINEAR_API_KEY and GITHUB_TOKEN

# Run
python main.py --target qa    # QA release
python main.py --target prod  # Prod release
```

## Configuration

- `config/boards.yaml` — Linear teams, statuses, and GitHub branch settings
- `config/repos.yaml` — GitHub repos to scan for commits
- `.env` — API keys

## Release Targets

| Target | Source Branch | Target Branch | Linear Status |
|--------|---------------|---------------|---------------|
| QA | `dev` | `qa` | "Ready to Deploy- QA" |
| Prod | `qa` | `main` | "Approved for Prod" |

See [SKILL.md](./SKILL.md) for full documentation.
