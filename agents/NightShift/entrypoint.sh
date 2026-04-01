#!/bin/bash
set -e

echo "=============================================="
echo "  NightShift — Autonomous Development Agent"
echo "=============================================="

# ── SSH Key Setup ────────────────────────────────────────
if [ -f /root/.ssh/id_ed25519 ]; then
    cp /root/.ssh/id_ed25519 /tmp/ssh_key
    chmod 600 /tmp/ssh_key
    export GIT_SSH_COMMAND="ssh -i /tmp/ssh_key -o StrictHostKeyChecking=no"
    echo "  SSH key found and configured"
fi

# ── Claude Code Auth ─────────────────────────────────────
if [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
    echo "  Claude Code: using CLAUDE_CODE_OAUTH_TOKEN"
fi

if [ -f /root/.claude.json ] || [ -f /root/.claude/credentials.json ]; then
    echo "  Claude Code credentials mounted"
else
    # Try to restore from backup
    BACKUP=$(ls /root/.claude/backups/.claude.json.backup.* 2>/dev/null | tail -1)
    if [ -n "$BACKUP" ]; then
        cp "$BACKUP" /root/.claude.json
        echo "  Claude Code credentials restored from backup"
    fi
fi

# ── GitHub CLI Auth ──────────────────────────────────────
if [ -n "$GH_TOKEN" ]; then
    echo "  GitHub CLI auth via GH_TOKEN"
fi

echo ""
echo "  Config:"
echo "    GITHUB_ORG=${GITHUB_ORG:-ruh-ai}"
echo "    TARGET_BRANCH=${TARGET_BRANCH:-dev}"
echo "    POLL_INTERVAL=${POLL_INTERVAL_MINUTES:-60}min"
echo "    MAX_CONCURRENT=${MAX_CONCURRENT_TICKETS:-2}"
echo "    CLAUDE_CMD=${CLAUDE_CMD:-claude}"
echo ""
echo "  Starting NightShift..."
echo "=============================================="

exec python3 main.py
