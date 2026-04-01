# PR Review Bot

Automated AI-powered PR review bot using Claude. Posts inline review comments on GitHub PRs and notifies authors via Slack DM.

## Setup

1. Copy `.env.example` to `.env` and fill in your API keys
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### GitHub Webhook

1. Go to your repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://your-server/webhook/github`
3. Content type: `application/json`
4. Secret: same as `WEBHOOK_SECRET` in `.env`
5. Events: select "Pull requests"

### Slack Bot

1. Create app at https://api.slack.com/apps
2. Add Bot Token Scopes: `chat:write`, `users:read`, `users:read.email`
3. Install to workspace
4. Copy Bot User OAuth Token to `SLACK_BOT_TOKEN` in `.env`

### CONTEXT.md

Add a `CONTEXT.md` file to your repo root describing your project's architecture, conventions, and tech stack. The bot uses this for context-aware reviews.

### User Mapping

Edit `user_mapping.yml` to map GitHub usernames to Slack user IDs for reliable DM delivery.

## Docker

```bash
docker build -t pr-review-bot .
docker run -d --env-file .env -p 8000:8000 --restart unless-stopped pr-review-bot
```

## Testing

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```
