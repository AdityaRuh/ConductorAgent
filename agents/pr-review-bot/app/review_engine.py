import json
import logging
import re

import anthropic
import httpx

from app.models import ReviewResult

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def build_system_prompt(review_rules: dict) -> str:
    checklist_items = review_rules.get("checklist", [])
    checklist_str = "\n".join(f"- {item}" for item in checklist_items)

    return f"""You are a senior code reviewer. Review the provided pull request diff thoroughly.

Review for:
1. Code quality & best practices
2. Security vulnerabilities (OWASP top 10)
3. Potential bugs & logical errors
4. Performance issues

Compliance checklist to evaluate:
{checklist_str}

Respond with ONLY valid JSON in this exact format:
{{
  "summary": "Brief overall assessment (1-2 sentences)",
  "risk_level": "low | medium | high",
  "findings": [
    {{
      "file": "path/to/file.py",
      "line": 42,
      "severity": "error | warning | suggestion",
      "category": "security | bug | style | performance",
      "comment": "Clear, actionable description of the issue and how to fix it"
    }}
  ],
  "checklist": {{
    "has_tests": true,
    "no_secrets": true
  }}
}}

IMPORTANT:
- The "line" field must be the line number as it appears in the NEW version of the file (the + side of the diff).
- Only report real issues. Do not fabricate findings.
- Be specific and actionable in your comments.
- For the checklist, evaluate each item as true/false based on the diff."""


def build_user_prompt(pr_title: str, pr_description: str, diff: str, context_md: str | None, is_incremental: bool) -> str:
    parts = []
    if is_incremental:
        parts.append("## Review Scope\nThis is an INCREMENTAL review. Only review the new changes below (not the full PR).\n")
    parts.append(f"## PR Title\n{pr_title}\n")
    if pr_description:
        parts.append(f"## PR Description\n{pr_description}\n")
    if context_md:
        parts.append(f"## CONTEXT.md (project architecture & conventions)\n{context_md}\n")
    parts.append(f"## Diff\n```diff\n{diff}\n```")
    return "\n".join(parts)


def parse_review_response(raw: str) -> ReviewResult:
    try:
        data = json.loads(raw)
        return ReviewResult.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        return ReviewResult.model_validate(data)
    raise ValueError(f"Could not parse review response as JSON: {raw[:200]}")


class ReviewEngine:
    def __init__(self, provider: str, api_key: str, model: str):
        self._provider = provider
        self._model = model
        if provider == "anthropic":
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            self._openrouter_model = f"anthropic/{model}" if not model.startswith("anthropic/") else model
            self._openrouter_key = api_key
            self._http = httpx.AsyncClient(timeout=120.0)

    async def review(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        if self._provider == "anthropic":
            return await self._review_anthropic(system_prompt, user_prompt)
        else:
            return await self._review_openrouter(system_prompt, user_prompt)

    async def _review_anthropic(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        msg = await self._anthropic_client.messages.create(
            model=self._model, max_tokens=4096, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = msg.content[0].text
        return parse_review_response(raw)

    async def _review_openrouter(self, system_prompt: str, user_prompt: str) -> ReviewResult:
        resp = await self._http.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {self._openrouter_key}", "Content-Type": "application/json"},
            json={"model": self._openrouter_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "max_tokens": 4096},
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        return parse_review_response(raw)

    async def close(self):
        if self._provider == "anthropic":
            await self._anthropic_client.close()
        else:
            await self._http.aclose()
