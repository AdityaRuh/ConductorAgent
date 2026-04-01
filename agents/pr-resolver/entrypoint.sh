#!/bin/bash
set -euo pipefail

echo "=== PR Resolver Agent ==="

# Authenticate gh CLI with GH_TOKEN
if [ -n "${GH_TOKEN:-}" ]; then
    echo "$GH_TOKEN" | gh auth login --with-token 2>/dev/null
    echo "  GitHub CLI: authenticated via GH_TOKEN"
else
    echo "  WARNING: GH_TOKEN not set — gh CLI will not work"
fi

# Auth: OpenClaw uses ANTHROPIC_OAUTH_TOKEN
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    export ANTHROPIC_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN"
    echo "  Claude auth: configured"
fi

echo "  LINEAR_API_KEY: ${LINEAR_API_KEY:+set}"
echo "  BOT_GITHUB_USER: ${BOT_GITHUB_USER:-AdityaRuh}"
echo "  TELEGRAM: ${TELEGRAM_BOT_TOKEN:+configured}"
echo "  Repos dir: ${REPOS_BASE_DIR:-/app/repos}"
echo ""

# Override repos dir to inside container
export REPOS_BASE_DIR="${REPOS_BASE_DIR:-/app/repos}"
mkdir -p "$REPOS_BASE_DIR"

# Run the resolver loop (polls every 30 min)
echo "Starting PR Resolver (30-min polling cycle)..."
while true; do
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running cycle..."
    bash /app/lib/pr-resolver.sh || echo "Cycle failed, will retry next interval"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Sleeping 30 minutes..."
    sleep 1800
done
