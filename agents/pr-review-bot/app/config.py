import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass
class Config:
    # LLM
    anthropic_api_key: str | None
    openrouter_api_key: str | None
    llm_provider: str
    claude_model: str

    # GitHub
    github_pat: str
    webhook_secret: str

    # Slack
    slack_bot_token: str
    slack_fallback_channel: str | None

    # Bot identity
    bot_github_username: str | None

    # Slack PR reviews channel (configurable)
    slack_pr_reviews_channel: str | None = None

    # OpenClaw integration
    openclaw_enabled: bool = False
    openclaw_base_url: str = "http://127.0.0.1:18789"
    openclaw_webhook_token: str = ""

    # Review rules
    review_rules: dict[str, Any] = field(default_factory=dict)

    # Slack user mapping (github_username -> slack_user_id)
    user_mapping: dict[str, str] = field(default_factory=dict)

    # Repos to exclude from review (full name or short name)
    excluded_repos: list[str] = field(default_factory=list)

    # Linear integration
    linear_api_key: str | None = None


def _load_review_rules() -> dict[str, Any]:
    rules_path = Path(__file__).parent.parent / "review_rules" / "default.yml"
    if rules_path.exists():
        with open(rules_path) as f:
            return yaml.safe_load(f)
    return {}


def _load_user_mapping() -> dict[str, str]:
    mapping_path = Path(__file__).parent.parent / "user_mapping.yml"
    if mapping_path.exists():
        with open(mapping_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _detect_provider(anthropic_key: str | None, openrouter_key: str | None, explicit: str | None) -> str:
    if explicit and explicit in ("anthropic", "openrouter"):
        return explicit
    if anthropic_key:
        return "anthropic"
    if openrouter_key:
        return "openrouter"
    raise ValueError("At least one LLM API key (ANTHROPIC_API_KEY or OPENROUTER_API_KEY) must be set")


_config: Config | None = None


def get_config() -> Config:
    global _config

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or None
    openrouter_key = os.environ.get("OPENROUTER_API_KEY") or None
    explicit_provider = os.environ.get("LLM_PROVIDER") or None

    provider = _detect_provider(anthropic_key, openrouter_key, explicit_provider)

    openclaw_enabled = os.environ.get("OPENCLAW_ENABLED", "").lower() in ("true", "1", "yes")
    openclaw_token = os.environ.get("OPENCLAW_WEBHOOK_TOKEN", "")

    _config = Config(
        anthropic_api_key=anthropic_key,
        openrouter_api_key=openrouter_key,
        llm_provider=provider,
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
        github_pat=os.environ["GITHUB_PAT"],
        webhook_secret=os.environ["WEBHOOK_SECRET"],
        slack_bot_token=os.environ["SLACK_BOT_TOKEN"],
        slack_fallback_channel=os.environ.get("SLACK_FALLBACK_CHANNEL") or None,
        slack_pr_reviews_channel=os.environ.get("SLACK_PR_REVIEWS_CHANNEL") or None,
        bot_github_username=os.environ.get("BOT_GITHUB_USERNAME") or None,
        openclaw_enabled=openclaw_enabled,
        openclaw_base_url=os.environ.get("OPENCLAW_BASE_URL", "http://127.0.0.1:18789"),
        openclaw_webhook_token=openclaw_token,
        review_rules=_load_review_rules(),
        user_mapping=_load_user_mapping(),
        excluded_repos=[r.strip() for r in os.environ.get("EXCLUDED_REPOS", "").split(",") if r.strip()],
        linear_api_key=os.environ.get("LINEAR_API_KEY") or None,
    )
    return _config
