#!/bin/bash
set -euo pipefail

echo "=== PR Automation Agent ==="

# Authenticate gh CLI
if [ -n "${GH_TOKEN:-}" ]; then
    echo "$GH_TOKEN" | gh auth login --with-token 2>/dev/null
    echo "  GitHub CLI: authenticated via GH_TOKEN"
fi

# Set GITHUB_TOKEN for PyGithub (uses this env var name)
export GITHUB_TOKEN="${GITHUB_TOKEN:-$GH_TOKEN}"

echo "  LINEAR_API_KEY: ${LINEAR_API_KEY:+set}"
echo "  GITHUB_ORG: ${GITHUB_ORG:-ruh-ai}"
echo "  Target: ${RELEASE_TARGET:-qa}"
echo ""

cd /app/github-linear-automation

# Run with target argument (default: qa)
exec python main.py --target "${RELEASE_TARGET:-qa}"
