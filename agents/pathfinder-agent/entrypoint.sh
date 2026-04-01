#!/bin/bash
set -euo pipefail

echo "=== Pathfinder Agent ==="
echo "Starting OpenClaw agent with Pathfinder workspace..."

# Auth: OpenClaw uses ANTHROPIC_OAUTH_TOKEN or CLAUDE_CODE_OAUTH_TOKEN
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    export ANTHROPIC_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN"
    echo "  Claude auth: configured via CLAUDE_CODE_OAUTH_TOKEN"
fi

# Verify Linear API key
echo "  LINEAR_API_KEY: ${LINEAR_API_KEY:+set}"

echo "  Workspace: /app"
echo "  Heartbeat: 30m"
echo ""

# Run openclaw in agent mode with this workspace
# Heartbeat is configured in HEARTBEAT.md — openclaw reads it automatically
exec openclaw agent \
    --workspace /app \
    --local \
    --heartbeat 30m \
    -p "Read HEARTBEAT.md and execute the full cycle. Process all Todo tickets."
