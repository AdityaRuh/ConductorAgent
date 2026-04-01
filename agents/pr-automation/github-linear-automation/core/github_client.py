"""
core/github_client.py
Wraps PyGithub for branch and PR operations.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from github import Github, GithubException
from github.Repository import Repository

logger = logging.getLogger(__name__)


@dataclass
class PRInfo:
    number: int
    url: str
    title: str
    repo: str
    status: str   # open / merged / closed
    branch: str


class GitHubClient:
    def __init__(self) -> None:
        self._org_name = os.environ["GITHUB_ORG"]
        self._gh = Github(os.environ["GITHUB_TOKEN"])
        self._org = self._gh.get_organization(self._org_name)

    def get_repo(self, repo_name: str) -> Repository:
        return self._org.get_repo(repo_name)

    def branch_exists(self, repo: Repository, branch_name: str) -> bool:
        try:
            repo.get_branch(branch_name)
            return True
        except GithubException:
            return False

    def delete_branch(self, repo: Repository, branch_name: str) -> bool:
        try:
            repo.get_git_ref(f"heads/{branch_name}").delete()
            logger.info("Deleted branch %s in %s", branch_name, repo.name)
            return True
        except GithubException as exc:
            logger.warning("Could not delete branch %s/%s: %s", repo.name, branch_name, exc)
            return False

    def find_open_pr(self, repo: Repository, head_branch: str) -> Optional[PRInfo]:
        pulls = repo.get_pulls(state="open", head=f"{self._org_name}:{head_branch}")
        for pr in pulls:
            return PRInfo(
                number=pr.number,
                url=pr.html_url,
                title=pr.title,
                repo=repo.name,
                status="open",
                branch=head_branch,
            )
        return None

    def find_open_pr_for_base(self, repo: Repository, base_branch: str) -> Optional[PRInfo]:
        """Find any open PR targeting the base branch."""
        pulls = repo.get_pulls(state="open", base=base_branch)
        for pr in pulls:
            return PRInfo(
                number=pr.number,
                url=pr.html_url,
                title=pr.title,
                repo=repo.name,
                status="open",
                branch=pr.head.ref,
            )
        return None

    def get_pr_commits(self, repo: Repository, pr_number: int) -> List[str]:
        """Get list of commit SHAs in a PR."""
        pr = repo.get_pull(pr_number)
        return [c.sha for c in pr.get_commits()]

    def update_pr(
        self,
        repo: Repository,
        pr_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> PRInfo:
        """Update an existing PR's title, body, and/or labels."""
        pr = repo.get_pull(pr_number)
        if title:
            pr.edit(title=title)
        if body:
            pr.edit(body=body)
        if labels:
            for label_name in labels:
                try:
                    label = repo.get_label(label_name)
                except GithubException:
                    label = repo.create_label(label_name, "0075ca")
                pr.add_to_labels(label)
        logger.info("Updated PR #%d — %s", pr.number, pr.html_url)
        return PRInfo(
            number=pr.number,
            url=pr.html_url,
            title=pr.title,
            repo=repo.name,
            status="open",
            branch=pr.head.ref,
        )

    def create_pr(
        self,
        repo: Repository,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        labels: List[str],
    ) -> PRInfo:
        pr = repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
        )
        for label_name in labels:
            try:
                label = repo.get_label(label_name)
            except GithubException:
                label = repo.create_label(label_name, "0075ca")
            pr.add_to_labels(label)

        logger.info("Created PR #%d — %s", pr.number, pr.html_url)
        return PRInfo(
            number=pr.number,
            url=pr.html_url,
            title=pr.title,
            repo=repo.name,
            status="open",
            branch=head_branch,
        )
