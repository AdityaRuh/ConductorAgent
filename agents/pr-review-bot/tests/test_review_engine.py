import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.review_engine import ReviewEngine, build_system_prompt, build_user_prompt, parse_review_response
from app.models import ReviewResult, Severity, RiskLevel


def test_build_system_prompt():
    rules = {"checklist": ["has_tests", "no_secrets"], "severity_threshold": "suggestion"}
    prompt = build_system_prompt(rules)
    assert "senior code reviewer" in prompt.lower()
    assert "has_tests" in prompt
    assert "no_secrets" in prompt


def test_build_user_prompt_with_context():
    prompt = build_user_prompt(pr_title="Add auth", pr_description="Adds login endpoint", diff="diff --git a/auth.py\n+def login():", context_md="# Auth Service\nFlask app with JWT.", is_incremental=False)
    assert "Add auth" in prompt
    assert "CONTEXT.md" in prompt
    assert "diff --git" in prompt


def test_build_user_prompt_without_context():
    prompt = build_user_prompt(pr_title="Fix typo", pr_description="", diff="diff", context_md=None, is_incremental=False)
    assert "CONTEXT.md" not in prompt


def test_build_user_prompt_incremental():
    prompt = build_user_prompt(pr_title="Update", pr_description="", diff="diff", context_md=None, is_incremental=True)
    assert "incremental" in prompt.lower() or "new changes" in prompt.lower()


def test_parse_review_response_valid():
    raw = json.dumps({"summary": "Looks good", "risk_level": "low", "findings": [{"file": "a.py", "line": 1, "severity": "warning", "category": "style", "comment": "Naming"}], "checklist": {"has_tests": True}})
    result = parse_review_response(raw)
    assert isinstance(result, ReviewResult)
    assert result.risk_level == RiskLevel.LOW
    assert len(result.findings) == 1


def test_parse_review_response_extracts_json_from_markdown():
    raw = "Here is my review:\n```json\n" + json.dumps({"summary": "OK", "risk_level": "low", "findings": [], "checklist": {}}) + "\n```\nDone."
    result = parse_review_response(raw)
    assert isinstance(result, ReviewResult)


@pytest.mark.asyncio
async def test_review_engine_call_anthropic():
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps({"summary": "Clean code", "risk_level": "low", "findings": [], "checklist": {"has_tests": True}}))]
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    engine = ReviewEngine(provider="anthropic", api_key="sk-test", model="claude-sonnet-4-20250514")
    with patch.object(engine, "_anthropic_client", mock_client):
        result = await engine.review(system_prompt="You are a reviewer", user_prompt="Review this diff")
    assert isinstance(result, ReviewResult)
    assert result.summary == "Clean code"
