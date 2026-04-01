import logging
from pathlib import Path

import yaml
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from app.models import ReviewResult, Severity

logger = logging.getLogger(__name__)

MAPPING_PATH = Path(__file__).parent.parent / "user_mapping.yml"


def format_slack_message(repo: str, pr_number: int, pr_title: str, pr_url: str, result: ReviewResult, review_failed: bool = False, slack_user_id: str | None = None) -> str:
    assignee_mention = f" — <@{slack_user_id}>" if slack_user_id else ""
    lines = [f":mag: *PR Review: {repo}#{pr_number}*{assignee_mention}", f'"{pr_title}"', ""]
    if review_failed:
        lines.append(":warning: Inline review could not be posted to GitHub. See details below.")
        lines.append("")
    if not result.findings:
        lines.append(":white_check_mark: No issues found!")
    else:
        errors = sum(1 for f in result.findings if f.severity == Severity.ERROR)
        warnings = sum(1 for f in result.findings if f.severity == Severity.WARNING)
        suggestions = sum(1 for f in result.findings if f.severity == Severity.SUGGESTION)
        lines.append(f"Found {len(result.findings)} issue(s):")
        if errors:
            lines.append(f":red_circle: {errors} error(s) — {result.findings[next(i for i, f in enumerate(result.findings) if f.severity == Severity.ERROR)].comment}")
        if warnings:
            lines.append(f":large_yellow_circle: {warnings} warning(s)")
        if suggestions:
            lines.append(f":bulb: {suggestions} suggestion(s)")
    lines.append("")
    checklist_parts = []
    for key, val in result.checklist.items():
        icon = ":white_check_mark:" if val else ":x:"
        label = key.replace("_", " ").title()
        checklist_parts.append(f"{icon} {label}")
    if checklist_parts:
        lines.append("Checklist: " + " | ".join(checklist_parts))
    lines.append("")
    lines.append(f":arrow_right: <{pr_url}|View PR>")
    return "\n".join(lines)


class SlackNotifier:
    def __init__(self, token: str, fallback_channel: str | None, user_mapping: dict[str, str] | None = None, pr_reviews_channel: str | None = None):
        self._client = AsyncWebClient(token=token)
        self._fallback_channel = fallback_channel
        self._user_mapping = user_mapping or {}
        self._pr_reviews_channel = pr_reviews_channel
        self._user_cache: dict[str, str] = {}  # github_username -> slack_user_id (runtime cache)

    async def lookup_user(self, github_username: str, github_email: str | None) -> str | None:
        """Dynamically resolve a GitHub username to a Slack user ID.

        Resolution order:
        1. Static user_mapping (instant, for overrides/exceptions)
        2. In-memory cache (avoids repeated API calls within a session)
        3. Slack email lookup (if GitHub provides the email)
        4. Slack users.list search (match by display name, real name, or title containing the GitHub username)
        """
        # 1. Static mapping (highest priority — useful for overrides)
        if github_username in self._user_mapping:
            slack_id = self._user_mapping[github_username]
            self._user_cache[github_username] = slack_id
            return slack_id

        # 2. In-memory cache
        if github_username in self._user_cache:
            return self._user_cache[github_username]

        # 3. Email lookup
        if github_email:
            try:
                resp = await self._client.users_lookupByEmail(email=github_email)
                if resp["ok"]:
                    slack_id = resp["user"]["id"]
                    self._user_cache[github_username] = slack_id
                    self._persist_mapping(github_username, slack_id)
                    logger.info("Resolved %s -> %s via email lookup", github_username, slack_id)
                    return slack_id
            except SlackApiError as e:
                logger.debug("Slack email lookup failed for %s: %s", github_email, e)

        # 4. Search through Slack workspace members
        slack_id = await self._search_slack_user(github_username)
        if slack_id:
            self._user_cache[github_username] = slack_id
            self._persist_mapping(github_username, slack_id)
            logger.info("Resolved %s -> %s via workspace search", github_username, slack_id)
            return slack_id

        logger.warning("Could not resolve GitHub user '%s' to a Slack user", github_username)
        return None

    async def _search_slack_user(self, github_username: str) -> str | None:
        """Search Slack workspace for a user matching the GitHub username."""
        username_lower = github_username.lower()

        try:
            cursor = None
            while True:
                kwargs = {"limit": 200}
                if cursor:
                    kwargs["cursor"] = cursor

                resp = await self._client.users_list(**kwargs)
                if not resp["ok"]:
                    break

                for member in resp.get("members", []):
                    if member.get("deleted") or member.get("is_bot"):
                        continue

                    profile = member.get("profile", {})

                    # Match against multiple Slack profile fields
                    candidates = [
                        member.get("name", ""),                    # Slack username
                        profile.get("display_name", ""),           # Display name
                        profile.get("display_name_normalized", ""),
                        profile.get("real_name", ""),              # Real name
                        profile.get("real_name_normalized", ""),
                        profile.get("title", ""),                  # Title/role (users often put GitHub handle here)
                    ]

                    for candidate in candidates:
                        if not candidate:
                            continue
                        # Exact match on any field (case-insensitive)
                        if candidate.lower() == username_lower:
                            return member["id"]
                        # GitHub username contained in the field (e.g. title: "github: shivam-ruh")
                        if username_lower in candidate.lower():
                            return member["id"]

                # Pagination
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        except SlackApiError as e:
            logger.warning("Slack users.list search failed: %s", e)

        return None

    def _persist_mapping(self, github_username: str, slack_id: str) -> None:
        """Auto-save newly discovered mappings to user_mapping.yml for future use."""
        try:
            existing = {}
            if MAPPING_PATH.exists():
                with open(MAPPING_PATH) as f:
                    existing = yaml.safe_load(f) or {}

            if github_username not in existing:
                existing[github_username] = slack_id
                with open(MAPPING_PATH, "w") as f:
                    yaml.dump(existing, f, default_flow_style=False)
                logger.info("Auto-cached %s -> %s in %s", github_username, slack_id, MAPPING_PATH)
        except Exception as e:
            logger.warning("Failed to persist user mapping for %s: %s", github_username, e)

    async def send_review_notification(self, github_username: str, github_email: str | None, message: str) -> bool:
        sent = False

        # Always post to pr-reviews channel if configured
        if self._pr_reviews_channel:
            try:
                await self._client.chat_postMessage(channel=self._pr_reviews_channel, text=message)
                logger.info("Sent to pr-reviews channel %s", self._pr_reviews_channel)
                sent = True
            except SlackApiError as e:
                logger.error("Failed to send to pr-reviews channel %s: %s", self._pr_reviews_channel, e)

        # Also DM the PR author
        user_id = await self.lookup_user(github_username, github_email)
        if user_id:
            try:
                await self._client.chat_postMessage(channel=user_id, text=message)
                logger.info("Sent Slack DM to %s (user_id=%s)", github_username, user_id)
                sent = True
            except SlackApiError as e:
                logger.error("Failed to send Slack DM to %s: %s", github_username, e)

        # Fallback channel if neither pr-reviews channel nor DM worked
        if not sent and self._fallback_channel:
            try:
                await self._client.chat_postMessage(channel=self._fallback_channel, text=message)
                logger.info("Sent to fallback channel %s for user %s", self._fallback_channel, github_username)
                sent = True
            except SlackApiError as e:
                logger.error("Failed to send to fallback channel: %s", e)

        if not sent:
            logger.warning("Could not notify %s via Slack", github_username)
        return sent
