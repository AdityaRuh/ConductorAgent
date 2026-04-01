"""
core/cherry_pick.py
Clones a repo, creates a release branch, cherry-picks commits oldest-first,
pushes. Conflicts are skipped silently — no AI, no external calls.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from core.commit_scanner import CommitInfo

logger = logging.getLogger(__name__)


@dataclass
class ConflictDetail:
    commit_sha: str
    message: str
    ticket_ids: List[str]
    files: List[str] = field(default_factory=list)
    resolved: bool = False
    resolution_summary: Optional[str] = None


@dataclass
class CherryPickResult:
    repo: str
    release_branch: str
    success: bool
    commits_applied: List[CommitInfo] = field(default_factory=list)
    commits_skipped: List[CommitInfo] = field(default_factory=list)
    commits_already_merged: List[CommitInfo] = field(default_factory=list)  # Commits already in target branch
    conflicts: List[ConflictDetail] = field(default_factory=list)
    resolved_conflicts: List[ConflictDetail] = field(default_factory=list)
    error: Optional[str] = None
    has_file_changes: bool = False
    changed_files: List[str] = field(default_factory=list)
    env_changes: List[str] = field(default_factory=list)  # New env vars from .env.example


class CherryPickEngine:
    def __init__(self) -> None:
        self._org = os.environ["GITHUB_ORG"]
        self._token = os.environ["GITHUB_TOKEN"]

    def run(
        self,
        repo_name: str,
        commits: List[CommitInfo],
        release_branch: str,
        base_branch: str,
        resolve_conflicts: bool = False,
    ) -> CherryPickResult:
        if not commits:
            return CherryPickResult(
                repo=repo_name, release_branch=release_branch,
                success=False, error="No commits to cherry-pick",
            )

        tmpdir = tempfile.mkdtemp(prefix=f"cp_{repo_name}_")
        clone_url = f"https://{self._token}@github.com/{self._org}/{repo_name}.git"
        result = CherryPickResult(repo=repo_name, release_branch=release_branch, success=True)

        try:
            subprocess.run(["git", "clone", clone_url, tmpdir],
                           check=True, capture_output=True)
            self._git(tmpdir, ["config", "user.email", "automation@openclaw.io"])
            self._git(tmpdir, ["config", "user.name", "OpenClaw Automation"])
            self._git(tmpdir, ["checkout", base_branch])
            self._git(tmpdir, ["checkout", "-b", release_branch])

            for commit in commits:
                # Check if commit is already merged into base branch
                if self._is_commit_merged(tmpdir, commit.sha, base_branch):
                    result.commits_already_merged.append(commit)
                    logger.info(
                        "Skipping %s (%s) — already merged in %s",
                        commit.short_sha, commit.message, base_branch,
                    )
                    continue

                outcome = self._pick_one(tmpdir, commit)
                if outcome == "applied":
                    result.commits_applied.append(commit)
                elif outcome == "empty":
                    pass  # already applied, silently skip
                else:
                    conflict_files = self._conflict_files(tmpdir)
                    
                    # Attempt AI-powered conflict resolution if enabled
                    if resolve_conflicts and conflict_files:
                        resolution = self._resolve_conflict_with_ai(
                            tmpdir, commit, conflict_files
                        )
                        if resolution["success"]:
                            result.commits_applied.append(commit)
                            result.resolved_conflicts.append(ConflictDetail(
                                commit_sha=commit.sha, message=commit.message,
                                ticket_ids=commit.ticket_ids, files=conflict_files,
                                resolved=True, resolution_summary=resolution["summary"],
                            ))
                            logger.info(
                                "Resolved conflict on %s (%s) — %s",
                                commit.short_sha, commit.message, resolution["summary"],
                            )
                            continue
                    
                    # Reset state instead of abort (safer when cherry-pick didn't fully start)
                    subprocess.run(
                        ["git", "reset", "--hard", "HEAD"],
                        cwd=tmpdir, capture_output=True, check=False,
                    )
                    result.commits_skipped.append(commit)
                    result.conflicts.append(ConflictDetail(
                        commit_sha=commit.sha, message=commit.message,
                        ticket_ids=commit.ticket_ids, files=conflict_files,
                    ))
                    logger.warning(
                        "Conflict on %s (%s) — skipped. Files: %s",
                        commit.short_sha, commit.message, conflict_files,
                    )

            if not result.commits_applied:
                result.success = False
                result.error = "No commits could be applied"
                return result

            # Check if there are actual file changes vs base branch
            diff_check = subprocess.run(
                ["git", "diff", "--name-only", base_branch],
                cwd=tmpdir, capture_output=True, text=True,
            )
            changed_files = [f for f in diff_check.stdout.strip().splitlines() if f]
            result.changed_files = changed_files
            result.has_file_changes = len(changed_files) > 0

            # Check for .env.example changes
            if ".env.example" in changed_files:
                result.env_changes = self._detect_env_changes(tmpdir, base_branch)

            if not result.has_file_changes:
                logger.warning("No file changes detected vs %s — skipping push.", base_branch)
                return result

            # Push all individual commits (no squashing)
            self._git(tmpdir, ["push", "origin", release_branch])

            logger.info(
                "Pushed %s to %s (%d applied, %d skipped)",
                release_branch, repo_name,
                len(result.commits_applied), len(result.commits_skipped),
            )

        except subprocess.CalledProcessError as exc:
            # stderr is already a string when text=True
            if isinstance(exc.stderr, bytes):
                err = exc.stderr.decode(errors="replace")
            else:
                err = exc.stderr if exc.stderr else str(exc)
            result.success = False
            result.error = f"Git error: {err}"
            logger.error("Cherry-pick failed for %s: %s", repo_name, err)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        return result

    # ------------------------------------------------------------------ #

    def _pick_one(self, repo_dir: str, commit: CommitInfo) -> str:
        proc = subprocess.run(
            ["git", "cherry-pick", commit.sha],
            cwd=repo_dir, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return "applied"
        if "nothing to commit" in proc.stdout + proc.stderr:
            return "empty"
        return "conflict"

    @staticmethod
    def _is_commit_merged(repo_dir: str, commit_sha: str, base_branch: str) -> bool:
        """Check if a commit is already merged into the base branch."""
        # Method 1: Check if commit is an ancestor of base branch
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit_sha, base_branch],
            cwd=repo_dir, capture_output=True,
        )
        if proc.returncode == 0:
            return True
        
        # Method 2: Check if commit's changes are already present (cherry-pick equivalent)
        # by looking for commits with the same patch-id
        patch_id_proc = subprocess.run(
            ["git", "show", commit_sha, "--format="],
            cwd=repo_dir, capture_output=True,
        )
        if patch_id_proc.returncode != 0:
            return False
        
        # Get the patch-id of the commit
        patch_id_calc = subprocess.run(
            ["git", "patch-id", "--stable"],
            cwd=repo_dir, input=patch_id_proc.stdout, capture_output=True,
        )
        if patch_id_calc.returncode != 0 or not patch_id_calc.stdout.strip():
            return False
        
        source_patch_id = patch_id_calc.stdout.decode().split()[0] if patch_id_calc.stdout else ""
        if not source_patch_id:
            return False
        
        # Check if any commit in base branch has the same patch-id
        log_proc = subprocess.run(
            ["git", "log", base_branch, "--format=%H", "-n", "200"],
            cwd=repo_dir, capture_output=True, text=True,
        )
        for line in log_proc.stdout.strip().splitlines():
            if not line:
                continue
            existing_sha = line.strip()
            existing_patch = subprocess.run(
                ["git", "show", existing_sha, "--format="],
                cwd=repo_dir, capture_output=True,
            )
            if existing_patch.returncode != 0:
                continue
            existing_patch_id_calc = subprocess.run(
                ["git", "patch-id", "--stable"],
                cwd=repo_dir, input=existing_patch.stdout, capture_output=True,
            )
            if existing_patch_id_calc.returncode == 0 and existing_patch_id_calc.stdout:
                existing_patch_id = existing_patch_id_calc.stdout.decode().split()[0]
                if existing_patch_id == source_patch_id:
                    return True
        
        return False

    @staticmethod
    def _conflict_files(repo_dir: str) -> List[str]:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=repo_dir, capture_output=True, text=True,
        )
        return [f for f in proc.stdout.strip().splitlines() if f]

    @staticmethod
    def _git(repo_dir: str, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args, cwd=repo_dir,
            check=True, capture_output=True, text=True,
        )

    @staticmethod
    def _detect_env_changes(repo_dir: str, base_branch: str) -> List[str]:
        """Detect new env vars added to .env.example vs base branch."""
        import re
        
        # Get .env.example from base branch
        base_env = subprocess.run(
            ["git", "show", f"{base_branch}:.env.example"],
            cwd=repo_dir, capture_output=True, text=True,
        )
        base_vars = set(re.findall(r"^([A-Z_][A-Z0-9_]*)=", base_env.stdout, re.MULTILINE))
        
        # Get current .env.example
        try:
            with open(f"{repo_dir}/.env.example") as f:
                current_content = f.read()
        except FileNotFoundError:
            return []
        
        current_vars = set(re.findall(r"^([A-Z_][A-Z0-9_]*)=", current_content, re.MULTILINE))
        
        # Find new vars
        new_vars = sorted(current_vars - base_vars)
        if new_vars:
            logger.info("New env vars in .env.example: %s", new_vars)
        return new_vars

    def _resolve_conflict_with_ai(
        self, repo_dir: str, commit: "CommitInfo", conflict_files: List[str]
    ) -> dict:
        """
        Attempt to resolve merge conflicts using Claude CLI.
        Returns {"success": bool, "summary": str}
        """
        import os
        import shutil

        # Check if claude CLI is available
        claude_path = shutil.which("claude")
        if not claude_path:
            logger.warning("claude CLI not found — skipping AI resolution")
            return {"success": False, "summary": "claude CLI not installed"}

        try:
            resolved_files = []

            for filepath in conflict_files:
                full_path = os.path.join(repo_dir, filepath)
                if not os.path.exists(full_path):
                    continue

                with open(full_path, "r") as f:
                    conflicted_content = f.read()

                # Skip if no conflict markers
                if "<<<<<<<" not in conflicted_content:
                    continue

                prompt = f"""You are resolving a git merge conflict. The commit being cherry-picked is:
Commit: {commit.sha[:8]}
Message: {commit.message}
Tickets: {', '.join(commit.ticket_ids)}

The file with conflicts is: {filepath}

Here is the conflicted file content:
```
{conflicted_content}
```

Rules:
1. Keep BOTH changes where they don't conflict semantically
2. For true conflicts, prefer the incoming changes (the commit being cherry-picked) since that's the new feature/fix
3. Remove all conflict markers (<<<<<<<, =======, >>>>>>>)
4. Ensure the result is valid, syntactically correct code
5. Do not add any comments about the merge

Return ONLY the resolved file content, nothing else. No explanations, no markdown code blocks."""

                # Use claude CLI with --print for non-interactive output
                proc = subprocess.run(
                    ["claude", "--print", "-p", prompt],
                    capture_output=True, text=True, timeout=120,
                )

                if proc.returncode != 0:
                    logger.warning("claude CLI failed for %s: %s", filepath, proc.stderr)
                    continue

                resolved_content = proc.stdout.strip()

                # Validate no conflict markers remain
                if "<<<<<<<" in resolved_content or ">>>>>>>" in resolved_content:
                    logger.warning("AI resolution still contains conflict markers for %s", filepath)
                    continue

                # Write resolved content
                with open(full_path, "w") as f:
                    f.write(resolved_content)

                resolved_files.append(filepath)

            if not resolved_files:
                return {"success": False, "summary": "Could not resolve conflicts"}

            # Stage resolved files
            for filepath in resolved_files:
                subprocess.run(
                    ["git", "add", filepath],
                    cwd=repo_dir, capture_output=True, check=True,
                )

            # Complete the cherry-pick
            subprocess.run(
                ["git", "cherry-pick", "--continue"],
                cwd=repo_dir, capture_output=True, check=False,
                env={**os.environ, "GIT_EDITOR": "true"},
            )

            summary = f"AI resolved {len(resolved_files)} file(s): {', '.join(resolved_files)}"
            return {"success": True, "summary": summary}

        except subprocess.TimeoutExpired:
            logger.error("claude CLI timed out")
            subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=repo_dir, capture_output=True, check=False,
            )
            return {"success": False, "summary": "claude CLI timed out"}
        except Exception as exc:
            logger.error("AI conflict resolution failed: %s", exc)
            # Reset to clean state
            subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=repo_dir, capture_output=True, check=False,
            )
            return {"success": False, "summary": str(exc)}
