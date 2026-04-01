"""
core/release_manager.py
Orchestrates one full release cycle (QA or Prod):
  Phase 1 — Discover Jira tickets
  Phase 2 — Scan repos for matching commits
  Phase 3 — Cherry-pick onto release branch
  Phase 4 — Create PRs
  Phase 5 — Log summary
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import yaml

from core.cherry_pick import CherryPickEngine, CherryPickResult
from core.commit_scanner import CommitInfo, CommitScanner
from core.github_client import GitHubClient, PRInfo
from core.linear_client import LinearClient, LinearTicket

logger = logging.getLogger(__name__)

_BOARDS_CONFIG = Path(__file__).parent.parent / "config" / "boards.yaml"

# Valid release targets
VALID_TARGETS = ("qa", "prod")


def _load_config() -> dict:
    with open(_BOARDS_CONFIG) as f:
        return yaml.safe_load(f)


def _load_release_config(target: str) -> dict:
    """Load GitHub config for a specific release target."""
    cfg = _load_config()
    releases = cfg.get("releases", {})
    release_cfg = releases.get(target, {})
    return release_cfg.get("github", {})


class ReleaseManager:
    def __init__(self, release_target: str = "qa") -> None:
        """
        Initialize ReleaseManager for a specific release target.
        
        Args:
            release_target: Either "qa" or "prod".
        
        Raises:
            ValueError: If release_target is not valid.
        """
        if release_target not in VALID_TARGETS:
            raise ValueError(f"Invalid release target '{release_target}'. Must be one of: {VALID_TARGETS}")
        
        self._release_target = release_target
        self._linear = LinearClient(release_target=release_target)
        self._github = GitHubClient()
        self._picker = CherryPickEngine()
        
        gh = _load_release_config(release_target)
        self._base_branch: str = gh.get("base_branch", "develop")
        self._source_branch: str = gh.get("source_branch")  # Branch to scan for commits
        self._branch_prefix: str = gh.get("release_branch_prefix", f"release/{release_target}-")
        self._pr_labels: List[str] = gh.get("pr_labels", [f"{release_target}-release"])
        
        # Initialize scanner with source branch restriction
        self._scanner = CommitScanner(source_branch=self._source_branch)
        
        # Release display name
        cfg = _load_config()
        release_cfg = cfg.get("releases", {}).get(release_target, {})
        self._release_name: str = release_cfg.get("name", release_target.upper())

    def run_release(self, resolve_conflicts: bool = False) -> Dict[str, PRInfo]:
        """Run the full pipeline. Returns {repo_name: PRInfo} for created PRs."""

        logger.info("=" * 60)
        logger.info("🍒 Starting %s", self._release_name)
        logger.info("   Target branch: %s", self._base_branch)
        logger.info("   Source branch: %s", self._source_branch or "all branches")
        logger.info("=" * 60)

        # ── Phase 1: Tickets ──────────────────────────────────────────
        logger.info("Phase 1 — Discovering Linear tickets …")
        tickets = self._linear.get_qa_ready_tickets()
        if not tickets:
            logger.info("No tickets found in target status — nothing to do.")
            return {}

        ticket_map: Dict[str, LinearTicket] = {t.key: t for t in tickets}
        ticket_ids = list(ticket_map.keys())
        logger.info("Tickets: %s", ticket_ids)

        # ── Phase 2: Scan repos ───────────────────────────────────────
        logger.info("Phase 2 — Scanning repos for commits …")
        commit_map = self._scanner.scan(ticket_ids)

        # Flatten to {repo_name: [CommitInfo]}, de-duped, sorted oldest→newest
        repo_commits: Dict[str, List[CommitInfo]] = defaultdict(list)
        seen_per_repo: Dict[str, set] = defaultdict(set)
        for tid, repos in commit_map.items():
            for repo_name, commits in repos.items():
                for c in commits:
                    if c.sha not in seen_per_repo[repo_name]:
                        seen_per_repo[repo_name].add(c.sha)
                        repo_commits[repo_name].append(c)

        for repo_name in repo_commits:
            repo_commits[repo_name].sort(key=lambda c: c.timestamp)

        if not repo_commits:
            logger.info("No commits found for any ticket — nothing to do.")
            return {}

        logger.info("Repos with commits: %s", list(repo_commits.keys()))

        # ── Phase 3: Cherry-pick ──────────────────────────────────────
        logger.info("Phase 3 — Cherry-picking commits …")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
        release_branch = f"{self._branch_prefix}{ts}"

        cp_results: Dict[str, CherryPickResult] = {}
        for repo_name, commits in repo_commits.items():
            logger.info("  %s — %d commit(s)", repo_name, len(commits))
            cp_results[repo_name] = self._picker.run(
                repo_name, commits, release_branch, self._base_branch,
                resolve_conflicts=resolve_conflicts,
            )

        # ── Phase 4: Create PRs ───────────────────────────────────────
        logger.info("Phase 4 — Creating PRs …")
        created_prs: Dict[str, PRInfo] = {}

        for repo_name, cp in cp_results.items():
            if not cp.success or not cp.commits_applied:
                logger.warning("Skipping PR for %s — no commits applied.", repo_name)
                continue

            # Check if there are actual file changes
            if not cp.has_file_changes:
                logger.warning("Skipping PR for %s — no file changes.", repo_name)
                continue

            try:
                repo = self._github.get_repo(repo_name)
            except Exception as exc:
                logger.error("Cannot access repo %s: %s", repo_name, exc)
                continue

            # Only include tickets that actually have commits in this PR
            involved_ticket_ids = sorted(
                {tid for c in cp.commits_applied for tid in c.ticket_ids}
            )
            involved_tickets = {k: v for k, v in ticket_map.items() if k in involved_ticket_ids}

            # Check for existing PR on same release branch
            existing = self._github.find_open_pr(repo, release_branch)
            if existing:
                logger.info("PR already open for %s/%s — skipping.", repo_name, release_branch)
                created_prs[repo_name] = existing
                continue

            # Check for existing PR targeting base branch — update it if missing commits
            existing_base_pr = self._github.find_open_pr_for_base(repo, self._base_branch)
            if existing_base_pr:
                existing_commits = set(self._github.get_pr_commits(repo, existing_base_pr.number))
                new_commits = [c for c in cp.commits_applied if c.sha not in existing_commits]
                
                if not new_commits:
                    logger.info("PR #%d already has all commits — skipping.", existing_base_pr.number)
                    created_prs[repo_name] = existing_base_pr
                    continue
                
                # Update existing PR with new info
                logger.info("Updating PR #%d with %d new commit(s).", existing_base_pr.number, len(new_commits))
                updated_pr = self._github.update_pr(
                    repo=repo,
                    pr_number=existing_base_pr.number,
                    title=self._pr_title(involved_ticket_ids, ts),
                    body=self._pr_body(involved_tickets, cp),
                    labels=self._pr_labels,
                )
                created_prs[repo_name] = updated_pr
                continue

            pr = self._github.create_pr(
                repo=repo,
                head_branch=release_branch,
                base_branch=self._base_branch,
                title=self._pr_title(involved_ticket_ids, ts),
                body=self._pr_body(involved_tickets, cp),
                labels=self._pr_labels,
            )
            created_prs[repo_name] = pr

        # ── Phase 5: Summary ──────────────────────────────────────────
        logger.info("Phase 5 — Summary")
        logger.info("=" * 60)
        logger.info("Release: %s → %s", self._release_name, self._base_branch)
        logger.info("=" * 60)
        
        # Tickets considered
        ticket_ids_str = ", ".join(t.key for t in tickets)
        logger.info("Tickets Considered (%d):", len(tickets))
        logger.info("  %s", ticket_ids_str)
        
        logger.info("-" * 60)
        
        # PRs Created/Updated
        logger.info("PRs Created/Updated (%d):", len(created_prs))
        for repo_name, pr in created_prs.items():
            logger.info("  → %s: %s", repo_name, pr.url)

        # Already merged commits grouped by repo — transition their tickets
        merged_by_repo: Dict[str, List[CommitInfo]] = defaultdict(list)
        for repo_name, res in cp_results.items():
            for c in res.commits_already_merged:
                merged_by_repo[repo_name].append(c)

        if merged_by_repo:
            logger.info("-" * 60)
            logger.info("Already Merged (Skipped):")
            logger.info("")
            
            # Collect all unique ticket IDs from already-merged commits
            merged_ticket_ids: set = set()
            for repo_name, commits in merged_by_repo.items():
                ticket_ids = sorted(set(tid for c in commits for tid in c.ticket_ids))
                ticket_ids_display = ", ".join(ticket_ids)
                logger.info("• %s: %s (%d commits)", repo_name, ticket_ids_display, len(commits))
                merged_ticket_ids.update(ticket_ids)
            
            # Transition already-merged tickets to the target status
            # Process subtasks first, then parent tickets (recursive check)
            transition_name = self._linear.get_merged_transition_name()
            if transition_name and merged_ticket_ids:
                logger.info("")
                logger.info("Transitioning already-merged tickets to '%s':", transition_name)
                logger.info("(Parent tickets only transition if all subtasks are in target status)")
                logger.info("")
                
                transitioned_set: set = set()
                for tid in sorted(merged_ticket_ids):
                    success = self._linear.transition_merged_ticket(tid, transitioned_set)
                    if success:
                        logger.info("  ✓ %s", tid)
                    # Failures are logged inside transition_merged_ticket with reason

        # Skipped commits grouped by repo with cherry-pick commands
        skipped_by_repo: Dict[str, List[CommitInfo]] = defaultdict(list)
        for repo_name, res in cp_results.items():
            for c in res.commits_skipped:
                skipped_by_repo[repo_name].append(c)

        if skipped_by_repo:
            logger.info("-" * 60)
            logger.info("Skipped Conflicts:")
            logger.info("")
            
            for repo_name, commits in skipped_by_repo.items():
                # Get unique ticket IDs for this repo
                ticket_ids = sorted(set(tid for c in commits for tid in c.ticket_ids))
                ticket_ids_display = ", ".join(ticket_ids)
                
                # Get all commit SHAs (short)
                all_shas = " ".join(c.short_sha for c in commits)
                
                logger.info("• %s: %s", repo_name, ticket_ids_display)
                logger.info("  ◦ git checkout %s && git pull && git checkout -b %s", self._base_branch, release_branch)
                logger.info("  ◦ git cherry-pick %s", all_shas)
                logger.info("")

        logger.info("=" * 60)

        return created_prs

    # Legacy method for backwards compatibility
    def run_qa_release(self, resolve_conflicts: bool = False) -> Dict[str, PRInfo]:
        """Legacy method — use run_release() instead."""
        return self.run_release(resolve_conflicts=resolve_conflicts)

    # ------------------------------------------------------------------ #

    def _pr_title(self, ticket_ids: List[str], ts: str) -> str:
        date_part = ts[:10]
        joined = ", ".join(ticket_ids[:5])
        if len(ticket_ids) > 5:
            joined += f" (+{len(ticket_ids) - 5} more)"
        
        # Different title prefix based on target
        prefix = "QA Release" if self._release_target == "qa" else "Prod Release"
        return f"[{prefix}] {joined} — {date_part}"

    def _pr_body(self, ticket_map: Dict[str, LinearTicket], cp: CherryPickResult) -> str:
        lines = ["## Tickets"]
        for key, t in ticket_map.items():
            lines.append(f"- **{key}**: {t.summary}")

        lines += ["", "## Commits Cherry-picked"]
        for c in cp.commits_applied:
            lines.append(f"- `{c.short_sha}` {c.message}")

        # File changes section
        if cp.changed_files:
            lines += ["", "## Files Changed"]
            for f in sorted(cp.changed_files):
                lines.append(f"- `{f}`")

        # Environment changes section
        if cp.env_changes:
            lines += ["", "## ⚠️ New Environment Variables"]
            lines.append("The following env vars were added to `.env.example` and need to be configured:")
            lines.append("")
            for var in cp.env_changes:
                lines.append(f"- `{var}`")

        # AI-resolved conflicts section
        if cp.resolved_conflicts:
            lines += ["", "## 🤖 AI-Resolved Conflicts"]
            lines.append("The following conflicts were automatically resolved:")
            lines.append("")
            for rc in cp.resolved_conflicts:
                lines.append(f"- `{rc.commit_sha[:8]}` {rc.message}")
                lines.append(f"  - Files: {', '.join(rc.files)}")
                if rc.resolution_summary:
                    lines.append(f"  - Resolution: {rc.resolution_summary}")

        # Already merged commits section
        if cp.commits_already_merged:
            lines += ["", "## ✅ Already Merged (Skipped)"]
            lines.append("The following commits were skipped because they are already in the target branch:")
            lines.append("")
            for c in cp.commits_already_merged:
                lines.append(f"- `{c.short_sha}` {c.message}")

        if cp.commits_skipped:
            lines += ["", "## ⚠️ Skipped (unresolved conflicts)"]
            for c in cp.commits_skipped:
                conflict = next((cf for cf in cp.conflicts if cf.commit_sha == c.sha), None)
                files = ", ".join(conflict.files) if conflict else "unknown"
                lines.append(f"- `{c.short_sha}` {c.message} — {files}")

        lines += ["", "---", "*Auto-generated by Cherry 🍒*"]
        return "\n".join(lines)
