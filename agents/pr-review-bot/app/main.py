"""PR Review Bot — Webhook proxy that triggers Sentinel via OpenClaw + Slack notification."""

import asyncio
import hashlib
import hmac
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException

from app.config import get_config
from app.github_client import GitHubClient
from app.slack_notifier import SlackNotifier
from app.linear_client import LinearClient, extract_ticket_id

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

_debounce: dict[str, float] = {}
DEBOUNCE_SECONDS = 30
_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    logger.info("PR Review Bot (thin proxy) starting — routing to OpenClaw sentinel-reviewer")
    yield
    logger.info("PR Review Bot shutting down")


app = FastAPI(title="PR Review Bot", lifespan=lifespan)


def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "sentinel-proxy", "uptime_seconds": int(time.time() - _start_time)}


@app.post("/webhook/github")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    cfg = get_config()
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(cfg.webhook_secret, body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"action": "ignored", "reason": f"event={event}"}

    payload = await request.json()
    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"action": "ignored", "reason": f"action={action}"}

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    # Skip draft PRs
    if pr.get("draft", False):
        return {"action": "ignored", "reason": "draft PR"}

    # Skip bot's own PRs
    pr_author = pr.get("user", {}).get("login", "")
    if cfg.bot_github_username and pr_author == cfg.bot_github_username:
        return {"action": "ignored", "reason": "bot PR"}

    # Skip excluded repos
    repo_full_name = repo.get("full_name", "")
    repo_short_name = repo.get("name", "")
    if repo_full_name in cfg.excluded_repos or repo_short_name in cfg.excluded_repos:
        logger.info("Skipping excluded repo: %s", repo_full_name)
        return {"action": "ignored", "reason": f"excluded repo: {repo_full_name}"}

    pr_key = f"{repo.get('full_name')}#{payload.get('number')}"

    if action == "synchronize":
        _debounce[pr_key] = time.time()
        background_tasks.add_task(_debounced_dispatch, pr_key=pr_key, payload=payload, action=action)
    else:
        background_tasks.add_task(dispatch_to_sentinel, payload=payload, action=action)

    return {"action": "dispatched", "pr": pr_key, "target": "sentinel-reviewer"}


async def _debounced_dispatch(pr_key: str, payload: dict, action: str):
    scheduled_at = _debounce.get(pr_key, 0)
    await asyncio.sleep(DEBOUNCE_SECONDS)
    if _debounce.get(pr_key, 0) != scheduled_at:
        logger.info("Debounced: skipping stale synchronize event for %s", pr_key)
        return
    await dispatch_to_sentinel(payload=payload, action=action)


async def dispatch_to_sentinel(payload: dict, action: str):
    """Forward PR event to Sentinel agent via OpenClaw, then send Slack notification."""
    cfg = get_config()
    pr = payload["pull_request"]
    repo = payload["repository"]
    full_name = repo["full_name"]
    pr_number = payload["number"]
    pr_title = pr["title"]
    pr_description = pr.get("body", "") or ""
    pr_author = pr["user"]["login"]
    pr_url = pr["html_url"]
    head_sha = pr["head"]["sha"]
    branch_name = pr["head"].get("ref", "")
    ticket_id = extract_ticket_id(branch_name)
    is_incremental = action == "synchronize"

    scope = "incremental (new push)" if is_incremental else "full (PR opened/reopened)"

    # Build the message for Sentinel — review + GitHub comment only, no Slack
    message = f"""## PR Review Request

**Repo:** {full_name}
**PR:** #{pr_number} — {pr_title}
**Author:** {pr_author}
**URL:** {pr_url}
**Action:** {action} ({scope})
**Head SHA:** {head_sha}
**Description:** {pr_description or '(none)'}

## Instructions

1. Fetch the diff using: gh pr diff {pr_number} --repo {full_name}
2. Review using the checklist in agents/pr-review-agent.md:
   - Coverage impact
   - Security scan
   - Breaking changes
   - Test quality
   - Pattern enforcement
3. Post a GitHub review comment using: gh pr review {pr_number} --repo {full_name} --comment --body "<your review>"
4. Do NOT send Slack notifications — the webhook proxy handles that.

{'This is a re-push (synchronize). Compare with your previous review in this session.' if is_incremental else 'This is a new PR. Do a full review.'}
"""

    session_key = f"hook:pr-review:{full_name}:{pr_number}"

    # Step 1: Dispatch to Sentinel (fire-and-forget to OpenClaw)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{cfg.openclaw_base_url}/hooks/agent",
                headers={
                    "Authorization": f"Bearer {cfg.openclaw_webhook_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "message": message,
                    "agentId": "sentinel-reviewer",
                    "name": f"PR Review: {full_name}#{pr_number}",
                    "sessionKey": session_key,
                    "wakeMode": "now",
                    "deliver": False,
                    "timeoutSeconds": 300,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Sentinel dispatched for %s#%d (runId=%s, session=%s)",
                full_name, pr_number, data.get("runId", "?"), session_key,
            )
        except Exception as e:
            logger.error("Failed to dispatch to Sentinel for %s#%d: %s", full_name, pr_number, e)
            return

    # Transition Linear ticket to "Code Review" when PR is opened
    if ticket_id and cfg.linear_api_key:
        await _transition_linear_ticket(cfg, ticket_id, "Code Review", pr_url)

    # Step 2: Poll for Sentinel's GitHub review, then send Slack notification
    review_body = await _poll_for_sentinel_review(full_name, pr_number, cfg.github_pat)

    if review_body:
        # Fetch GitHub user email for Slack lookup
        github = GitHubClient(pat=cfg.github_pat)
        try:
            author_email = await github.fetch_user_email(pr_author)
        except Exception:
            author_email = None
        finally:
            await github.close()

        await _send_slack_notification(
            cfg=cfg,
            full_name=full_name,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_url=pr_url,
            pr_author=pr_author,
            pr_author_email=author_email,
            review_body=review_body,
            is_incremental=is_incremental,
        )
        # Transition Linear ticket based on review outcome
        if ticket_id and cfg.linear_api_key:
            has_issues = "P1" in review_body or ":red_circle:" in review_body or "P2" in review_body
            if has_issues:
                # Issues found — try "Require Changes", fallback to "In Development"
                await _transition_linear_ticket(
                    cfg, ticket_id,
                    ["Require Changes", "In Development"],
                    pr_url,
                )
            else:
                # Clean review — try "Ready to Deploy - Dev", fallback to "Ready to Deploy"
                await _transition_linear_ticket(
                    cfg, ticket_id,
                    ["Ready to Deploy - Dev", "Ready to Deploy"],
                    pr_url,
                )
    else:
        logger.warning("No Sentinel review found for %s#%d after polling — skipping Slack", full_name, pr_number)


async def _poll_for_sentinel_review(full_name: str, pr_number: int, github_pat: str, max_wait: int = 300, interval: int = 15) -> str | None:
    """Poll the PR for a Sentinel review comment. Returns the review body or None.

    Skips early if the GitHub API returns 404 three times consecutively
    (e.g. PAT lacks access to a private repo).
    """
    MAX_404_RETRIES = 3
    consecutive_404s = 0

    owner, repo = full_name.split("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {github_pat}",
        "Accept": "application/vnd.github+json",
    }

    elapsed = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < max_wait:
            await asyncio.sleep(interval)
            elapsed += interval

            try:
                resp = await client.get(url, headers=headers)

                # Track consecutive 404s — skip if PAT lacks repo access
                if resp.status_code == 404:
                    consecutive_404s += 1
                    logger.warning(
                        "404 polling reviews for %s#%d (attempt %d/%d) — PAT may lack repo access",
                        full_name, pr_number, consecutive_404s, MAX_404_RETRIES,
                    )
                    if consecutive_404s >= MAX_404_RETRIES:
                        logger.error(
                            "Skipping review for %s#%d — got %d consecutive 404s. "
                            "Ensure the GitHub PAT has access to this repo.",
                            full_name, pr_number, MAX_404_RETRIES,
                        )
                        return None
                    continue

                # Reset counter on any non-404 response
                consecutive_404s = 0
                resp.raise_for_status()
                reviews = resp.json()

                # Look for a review containing Sentinel's marker
                for review in reversed(reviews):
                    body = review.get("body", "") or ""
                    if "Sentinel Review" in body or "Sentinel" in body:
                        logger.info("Found Sentinel review for %s#%d after %ds", full_name, pr_number, elapsed)
                        return body
            except httpx.HTTPStatusError as e:
                logger.warning("HTTP error polling reviews for %s#%d: %s", full_name, pr_number, e)
            except Exception as e:
                logger.warning("Error polling reviews for %s#%d: %s", full_name, pr_number, e)

            logger.debug("Polling for Sentinel review on %s#%d (%ds/%ds)", full_name, pr_number, elapsed, max_wait)

    return None


async def _send_slack_notification(
    cfg,
    full_name: str,
    pr_number: int,
    pr_title: str,
    pr_url: str,
    pr_author: str,
    pr_author_email: str | None,
    review_body: str,
    is_incremental: bool,
):
    """Send Slack notification based on Sentinel's GitHub review."""
    slack = SlackNotifier(
        token=cfg.slack_bot_token,
        fallback_channel=cfg.slack_fallback_channel,
        user_mapping=cfg.user_mapping,
        pr_reviews_channel=cfg.slack_pr_reviews_channel,
    )

    # Resolve PR author to Slack user ID
    slack_user_id = await slack.lookup_user(pr_author, pr_author_email)
    mention = f"<@{slack_user_id}>" if slack_user_id else f"@{pr_author} (GitHub)"

    # Parse findings from review body
    p1_count = review_body.count("P1")
    p2_count = review_body.count("P2")
    p3_count = review_body.count("P3")

    # Determine risk level from review
    if ":red_circle:" in review_body or "HIGH" in review_body:
        risk = ":red_circle: HIGH"
    elif "MEDIUM" in review_body or ":large_yellow_circle:" in review_body:
        risk = ":large_yellow_circle: MEDIUM"
    else:
        risk = ":white_circle: LOW"

    # Build Slack message
    prefix = ":recycle: Re-review" if is_incremental else ":shield: Sentinel Review"
    lines = [
        f"*{prefix}: {full_name} #{pr_number}*",
        f'"{pr_title}" — {mention}',
        "",
        f"*Risk:* {risk}",
        f"*Findings:* {p1_count} P1 · {p2_count} P2 · {p3_count} P3",
        "",
    ]

    # Extract P1 findings (lines starting with - and containing P1)
    for line in review_body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- ") and "P1" in stripped:
            lines.append(stripped)
        elif stripped.startswith("- :red_circle:") or stripped.startswith("- 🔴"):
            lines.append(stripped)

    if "No issues found" in review_body or "LGTM" in review_body:
        lines.append(":white_check_mark: No issues found. LGTM.")

    lines.append("")
    lines.append(f":arrow_right: <{pr_url}|View PR>")

    message = "\n".join(lines)

    try:
        await slack.send_review_notification(
            github_username=pr_author,
            github_email=pr_author_email,
            message=message,
        )
        logger.info("Slack notification sent for %s#%d", full_name, pr_number)
    except Exception as e:
        logger.error("Failed to send Slack notification for %s#%d: %s", full_name, pr_number, e)


async def _transition_linear_ticket(cfg, ticket_id: str, target_states: str | list[str], pr_url: str):
    """Transition a Linear ticket to the given state (tries multiple fallbacks)."""
    if isinstance(target_states, str):
        target_states = [target_states]
    linear = LinearClient(api_key=cfg.linear_api_key)
    try:
        new_state = None
        for state_name in target_states:
            new_state = await linear.transition_to_state_by_name(ticket_id, state_name)
            if new_state:
                break
        if new_state:
            logger.info("Linear: %s → '%s'", ticket_id, new_state)
            # Add a comment on the ticket linking to the PR
            issue = await linear.find_issue(ticket_id)
            if issue:
                comment = f"🤖 **Sentinel PR Review Bot**\n\nPR: {pr_url}\nStatus transitioned to **{new_state}**."
                await linear.add_comment(issue["id"], comment)
        else:
            logger.warning("Linear: could not transition %s to any of %s", ticket_id, target_states)
    except Exception as e:
        logger.error("Linear transition failed for %s: %s", ticket_id, e)
    finally:
        await linear.close()
