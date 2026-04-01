import json
import logging
import re

import httpx

from app.models import ReviewResult

logger = logging.getLogger(__name__)


class OpenClawClient:
    """Client that triggers the OpenClaw code-reviewer agent via the /hooks/agent endpoint."""

    def __init__(self, base_url: str, token: str, timeout: float = 180.0):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = httpx.AsyncClient(timeout=timeout)

    async def trigger_review(
        self,
        repo: str,
        pr_number: int,
        pr_title: str,
        pr_description: str,
        pr_author: str,
        action: str,
        diff: str,
        context_md: str | None,
        is_incremental: bool,
    ) -> ReviewResult:
        """Send PR data to OpenClaw agent and get structured review back synchronously."""

        scope = "incremental" if is_incremental else "full"
        context_section = ""
        if context_md:
            context_section = f"## Project Context\n{context_md}\n\n"

        message = (
            f"PR: {repo}#{pr_number}\n"
            f"Title: {pr_title}\n"
            f"Description: {pr_description or '(none)'}\n"
            f"Author: {pr_author}\n"
            f"Action: {action}\n"
            f"Scope: {scope}\n\n"
            f"{context_section}"
            f"## Diff\n```diff\n{diff}\n```"
        )

        payload = {
            "message": message,
            "agentId": "code-reviewer",
            "name": f"PR Review: {repo}#{pr_number}",
            "sessionKey": f"hook:pr-review:{repo}:{pr_number}",
            "wakeMode": "now",
            "deliver": False,
            "timeoutSeconds": 180,
        }

        resp = await self._http.post(
            f"{self._base_url}/hooks/agent",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        logger.info("OpenClaw response keys: %s", list(data.keys()))

        # The /hooks/agent endpoint returns the result synchronously
        if "result" in data:
            return self._parse_result(data["result"])

        # If we got a text/content response from the agent
        for key in ("text", "content", "response", "output"):
            if key in data:
                return self._parse_result(data[key])

        raise ValueError(f"Unexpected OpenClaw response: {json.dumps(data)[:300]}")

    def _parse_result(self, raw: str | dict) -> ReviewResult:
        """Parse the agent's JSON response into a ReviewResult."""
        if isinstance(raw, dict):
            return ReviewResult.model_validate(raw)

        # Try direct JSON parse
        try:
            data = json.loads(raw)
            return ReviewResult.model_validate(data)
        except (json.JSONDecodeError, Exception):
            pass

        # Try extracting JSON from markdown code blocks
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            return ReviewResult.model_validate(data)

        raise ValueError(f"Could not parse OpenClaw response as JSON: {str(raw)[:300]}")

    async def close(self):
        await self._http.aclose()
