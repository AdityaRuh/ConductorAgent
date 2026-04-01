import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from app.github_client import GitHubClient


@pytest.fixture
def client():
    return GitHubClient(pat="ghp_test")


@pytest.mark.asyncio
async def test_fetch_pr_diff(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "diff --git a/file.py b/file.py\n+new line"
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
        diff = await client.fetch_pr_diff("owner", "repo", 1)
        assert "diff --git" in diff


@pytest.mark.asyncio
async def test_fetch_context_md_found(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "# Project Context\nThis is a Python app."
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
        content = await client.fetch_context_md("owner", "repo", "feature-branch")
        assert "Python app" in content


@pytest.mark.asyncio
async def test_fetch_context_md_not_found(client):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response))

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
        content = await client.fetch_context_md("owner", "repo", "main")
        assert content is None


@pytest.mark.asyncio
async def test_post_review(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._http, "post", new_callable=AsyncMock, return_value=mock_response):
        await client.post_review(
            owner="owner",
            repo="repo",
            pr_number=1,
            commit_sha="abc123",
            body="Summary",
            comments=[{"path": "file.py", "line": 10, "side": "RIGHT", "body": "Issue here"}],
        )
        client._http.post.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_compare_diff(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "diff for new commits"
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
        diff = await client.fetch_compare_diff("owner", "repo", "sha1", "sha2")
        assert "diff for new commits" in diff
