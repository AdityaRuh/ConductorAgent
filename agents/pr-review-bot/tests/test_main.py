import hashlib
import hmac
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


def make_signature(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.webhook_secret = "test-secret"
    config.github_pat = "ghp_test"
    config.anthropic_api_key = "sk-ant-test"
    config.openrouter_api_key = None
    config.llm_provider = "anthropic"
    config.claude_model = "claude-sonnet-4-20250514"
    config.slack_bot_token = "xoxb-test"
    config.slack_fallback_channel = None
    config.bot_github_username = None
    config.review_rules = {"checklist": ["has_tests"], "skip_files": [], "skip_options": {"draft_prs": True}}
    config.user_mapping = {}
    return config


@pytest.fixture
def client(mock_config):
    with patch("app.main.get_config", return_value=mock_config):
        from app.main import app
        with TestClient(app) as c:
            yield c


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_webhook_invalid_signature(client):
    payload = json.dumps({"action": "opened"}).encode()
    resp = client.post(
        "/webhook/github",
        content=payload,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=invalid", "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 403


def test_webhook_ignores_non_pr_event(client):
    payload = json.dumps({"action": "created"}).encode()
    sig = make_signature("test-secret", payload)
    resp = client.post(
        "/webhook/github",
        content=payload,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig, "X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "ignored"


def test_webhook_ignores_unhandled_action(client):
    payload = json.dumps({"action": "closed"}).encode()
    sig = make_signature("test-secret", payload)
    resp = client.post(
        "/webhook/github",
        content=payload,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig, "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "ignored"


def test_webhook_accepts_valid_opened_pr(client, mock_config):
    payload_dict = {
        "action": "opened",
        "number": 1,
        "pull_request": {
            "title": "Test PR", "body": "Description", "draft": False,
            "user": {"login": "testuser"},
            "head": {"sha": "abc123", "ref": "feature-branch"},
            "html_url": "https://github.com/owner/repo/pull/1",
        },
        "repository": {"full_name": "owner/repo", "owner": {"login": "owner"}, "name": "repo"},
    }
    payload = json.dumps(payload_dict).encode()
    sig = make_signature("test-secret", payload)

    with patch("app.main.process_review", new_callable=AsyncMock):
        resp = client.post(
            "/webhook/github",
            content=payload,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig, "X-GitHub-Event": "pull_request"},
        )
    assert resp.status_code == 200
    assert resp.json()["action"] == "processing"
