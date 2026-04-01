"""
core/commit_scanner.py
Scans GitHub repos for commits referencing Jira ticket IDs.
Runs in parallel using ThreadPoolExecutor (8 workers).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import yaml

logger = logging.getLogger(__name__)

_REPOS_CONFIG = Path(__file__).parent.parent / "config" / "repos.yaml"

# { ticket_id: { repo_name: [CommitInfo] } }
CommitMap = Dict[str, Dict[str, List["CommitInfo"]]]


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    message: str
    author: str
    timestamp: datetime
    repo: str
    ticket_ids: List[str] = field(default_factory=list)


def _load_repos_config() -> dict:
    with open(_REPOS_CONFIG) as f:
        return yaml.safe_load(f)


class CommitScanner:
    def __init__(self, source_branch: str = None) -> None:
        cfg = _load_repos_config()
        self._repos: List[dict] = cfg.get("repositories", [])
        self._pattern = re.compile(cfg.get("commit_pattern", r"([A-Z]+-\d+)"))
        self._org = os.environ["GITHUB_ORG"]
        self._token = os.environ["GITHUB_TOKEN"]
        self._source_branch = source_branch  # If set, only scan this branch

    def scan(self, ticket_ids: List[str]) -> CommitMap:
        if not self._repos:
            logger.warning("No repositories configured in config/repos.yaml")
            return {}

        commit_map: CommitMap = {tid: {} for tid in ticket_ids}
        tmpdir = tempfile.mkdtemp(prefix="jira_scan_")

        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {
                    executor.submit(self._scan_repo, r["name"], ticket_ids, tmpdir, self._source_branch): r["name"]
                    for r in self._repos
                }
                for future in as_completed(futures):
                    repo_name = futures[future]
                    try:
                        for tid, commits in future.result().items():
                            if commits:
                                commit_map[tid][repo_name] = commits
                    except Exception as exc:
                        logger.error("Scan failed for %s: %s", repo_name, exc)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        return commit_map

    # ------------------------------------------------------------------ #

    def _scan_repo(self, repo_name: str, ticket_ids: List[str], tmpdir: str, source_branch: str = None) -> Dict[str, List[CommitInfo]]:
        repo_dir = Path(tmpdir) / repo_name
        clone_url = f"https://{self._token}@github.com/{self._org}/{repo_name}.git"

        if not repo_dir.exists():
            logger.info("Cloning %s …", repo_name)
            subprocess.run(["git", "clone", "--mirror", clone_url, str(repo_dir)],
                           check=True, capture_output=True)
        else:
            subprocess.run(["git", "remote", "update"], cwd=str(repo_dir),
                           check=True, capture_output=True)

        results: Dict[str, List[CommitInfo]] = {tid: [] for tid in ticket_ids}

        # Determine branch to scan: specific branch or --all
        branch_ref = source_branch if source_branch else "--all"
        if source_branch:
            logger.debug("Scanning %s on branch %s only", repo_name, source_branch)

        for tid in ticket_ids:
            git_log_args = ["git", "log", "--format=%H|%h|%s|%an|%aI", f"--grep=^{tid}"]
            if source_branch:
                git_log_args.append(source_branch)
            else:
                git_log_args.append("--all")
            
            raw = subprocess.run(
                git_log_args,
                cwd=str(repo_dir), capture_output=True, text=True,
            )
            seen: set = set()
            for line in raw.stdout.strip().splitlines():
                parts = line.split("|", 4)
                if len(parts) < 5:
                    continue
                sha, short_sha, message, author, ts_raw = parts
                if sha in seen:
                    continue
                
                # Only include commits where message STARTS with ticket ID
                if not message.startswith(tid):
                    continue
                
                seen.add(sha)
                try:
                    timestamp = datetime.fromisoformat(ts_raw.strip())
                except ValueError:
                    timestamp = datetime.utcnow()

                results[tid].append(CommitInfo(
                    sha=sha, short_sha=short_sha, message=message,
                    author=author, timestamp=timestamp, repo=repo_name,
                    ticket_ids=list(set(self._pattern.findall(message))),
                ))

            results[tid].sort(key=lambda c: c.timestamp)

        return results
