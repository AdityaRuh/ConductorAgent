import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.slack_notifier import SlackNotifier, format_slack_message
from app.models import ReviewResult, ReviewFinding, Severity, Category, RiskLevel


@pytest.fixture
def sample_result():
    return ReviewResult(
        summary="Found some issues",
        risk_level=RiskLevel.MEDIUM,
        findings=[
            ReviewFinding(file="auth.py", line=42, severity=Severity.ERROR, category=Category.SECURITY, comment="SQL injection"),
            ReviewFinding(file="handler.py", line=15, severity=Severity.WARNING, category=Category.BUG, comment="Missing validation"),
            ReviewFinding(file="utils.py", line=88, severity=Severity.SUGGESTION, category=Category.STYLE, comment="Extract helper"),
        ],
        checklist={"has_tests": True, "no_secrets": True, "pr_description_complete": False},
    )


def test_format_slack_message(sample_result):
    msg = format_slack_message(repo="owner/repo", pr_number=42, pr_title="Add auth endpoint", pr_url="https://github.com/owner/repo/pull/42", result=sample_result)
    assert "owner/repo#42" in msg
    assert "Add auth endpoint" in msg
    assert "error" in msg.lower()
    assert "https://github.com/owner/repo/pull/42" in msg


def test_format_slack_message_no_findings():
    result = ReviewResult(summary="Clean code", risk_level=RiskLevel.LOW, findings=[], checklist={"has_tests": True})
    msg = format_slack_message(repo="owner/repo", pr_number=1, pr_title="Fix typo", pr_url="https://github.com/owner/repo/pull/1", result=result)
    assert "no issues" in msg.lower() or "clean" in msg.lower() or "0" in msg


@pytest.mark.asyncio
async def test_lookup_slack_user_by_email():
    mock_client = MagicMock()
    mock_client.users_lookupByEmail = AsyncMock(return_value={"ok": True, "user": {"id": "U123"}})
    notifier = SlackNotifier(token="xoxb-test", fallback_channel=None, user_mapping={})
    with patch.object(notifier, "_client", mock_client):
        user_id = await notifier.lookup_user(github_username="testuser", github_email="test@example.com")
        assert user_id == "U123"


@pytest.mark.asyncio
async def test_lookup_slack_user_by_mapping():
    notifier = SlackNotifier(token="xoxb-test", fallback_channel=None, user_mapping={"testuser": "U456"})
    user_id = await notifier.lookup_user(github_username="testuser", github_email=None)
    assert user_id == "U456"
