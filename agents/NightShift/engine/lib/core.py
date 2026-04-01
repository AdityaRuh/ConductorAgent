"""
Shared core logic for both main.py (continuous loop) and run_once.py (single scan).

Architecture: 3-phase processing
  Phase 1 — COLLECT: fetch all issues, filter, sort by priority
  Phase 2 — PREPARE: clone/update all unique repos in parallel
  Phase 3 — EXECUTE: process tickets in parallel (max N workers)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.config import (
    LINEAR_API_KEY, GITHUB_ORG, TARGET_BRANCH, LOGS_DIR,
    CLAUDE_CMD, REPOS_DIR, REPO_MAP, PROCESSING_LABEL, DONE_LABEL,
    MAX_CONCURRENT_TICKETS, MAX_CONCURRENT_REPOS, SENTINEL_SKILLS_PATH,
)
from lib.linear_client import LinearClient
from skills.developer_skill import DeveloperSkill, DeveloperResult
from skills.ticket_enricher import parse_acceptance_criteria
from skills.task_decomposer import should_decompose, decompose_and_create_subtasks


# ── Types ────────────────────────────────────────────────────────────────────

class RepoEntry:
    def __init__(self, name: str, clone_url: str | None = None) -> None:
        self.name = name
        self.clone_url = clone_url


# ── Init ─────────────────────────────────────────────────────────────────────

linear = LinearClient(LINEAR_API_KEY)
# Developer skill is initialized after we know the viewer_id (in process_tickets)
dev_skill: DeveloperSkill | None = None

os.makedirs(LOGS_DIR, exist_ok=True)

PROCESSED_FILE = os.path.join(LOGS_DIR, "processed_issues.json")
# Fully completed issues — skip entirely on next scan
processed_issues: set[str] = set()
# Tracks which repos succeeded per issue — on retry, only process failed repos
# Format: { "issue-id": ["repo-a", "repo-b"] }
COMPLETED_REPOS_FILE = os.path.join(LOGS_DIR, "completed_repos.json")
completed_repos: dict[str, list[str]] = {}

if os.path.exists(PROCESSED_FILE):
    try:
        with open(PROCESSED_FILE) as f:
            processed_issues = set(json.load(f))
    except Exception:
        pass
if os.path.exists(COMPLETED_REPOS_FILE):
    try:
        with open(COMPLETED_REPOS_FILE) as f:
            completed_repos = json.load(f)
    except Exception:
        pass

# Thread-safety locks
_processed_lock = threading.Lock()
_repo_locks: dict[str, threading.Lock] = {}
_repo_locks_guard = threading.Lock()


def _get_repo_lock(repo_name: str) -> threading.Lock:
    """Get or create a per-repo lock to prevent concurrent git operations on the same repo."""
    with _repo_locks_guard:
        if repo_name not in _repo_locks:
            _repo_locks[repo_name] = threading.Lock()
        return _repo_locks[repo_name]


# ── Helpers ──────────────────────────────────────────────────────────────────

def save_processed() -> None:
    with _processed_lock:
        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(processed_issues), f, indent=2)


def save_completed_repos() -> None:
    with _processed_lock:
        with open(COMPLETED_REPOS_FILE, "w") as f:
            json.dump(completed_repos, f, indent=2)


def log(msg: str) -> None:
    ts = datetime.utcnow().isoformat() + "Z"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(os.path.join(LOGS_DIR, "automation.log"), "a") as f:
        f.write(line + "\n")


EXTRA_PATHS = ":".join([
    os.path.join(Path.home(), ".npm-global/bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
])


def shell(cmd: str, cwd: str | None = None, timeout: int = 600) -> str:
    env = {**os.environ, "PATH": f"{EXTRA_PATHS}:{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=cwd, timeout=timeout, env=env,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr,
        )
    return result.stdout.strip()


# ── Priority ─────────────────────────────────────────────────────────────────

# Linear priority: 0=none, 1=urgent, 2=high, 3=medium, 4=low
# Sort key: urgent first (1), then high (2), medium (3), low (4), none last (5)
PRIORITY_SORT_KEY = {1: 1, 2: 2, 3: 3, 4: 4, 0: 5}
PRIORITY_NAMES = {0: "None", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}


def _priority_sort_key(issue: dict[str, Any]) -> int:
    return PRIORITY_SORT_KEY.get(issue.get("priority", 0), 5)


# ── Repo Detection ───────────────────────────────────────────────────────────

def detect_repos(
    issue: dict[str, Any], labels: list[str], team_key: str, project_name: str | None
) -> list[RepoEntry]:
    seen: set[str] = set()
    repos: list[RepoEntry] = []

    def add_repo(name: str, clone_url: str | None = None) -> None:
        if name.lower() not in seen:
            seen.add(name.lower())
            repos.append(RepoEntry(name, clone_url))

    # 1. repo: labels
    for label in labels:
        if label.lower().startswith("repo:"):
            add_repo(label.split(":", 1)[1].strip())
    if repos:
        return repos

    # 2. GitHub URLs in description
    desc = issue.get("description") or ""
    for m in re.finditer(r"github\.com/([\w.-]+)/([\w.-]+)", desc):
        owner, repo = m.group(1), m.group(2).removesuffix(".git")
        add_repo(repo, f"git@github.com:{owner}/{repo}.git")
    if repos:
        return repos

    # 3. Text patterns: Repository: name / Repo: name
    for m in re.finditer(r"(?:repository|repo)\s*:\s*([\w.-]+)", desc, re.IGNORECASE):
        add_repo(m.group(1).strip())
    if repos:
        return repos

    # 4. Project name
    if project_name:
        return [RepoEntry(project_name.lower().replace(" ", "-"))]

    # 5. Team key fallback
    return [RepoEntry(team_key.lower())]


# ── Repo Management ─────────────────────────────────────────────────────────

def get_repo_path(repo_name: str, clone_url: str | None) -> str:
    repo_path = REPO_MAP.get(repo_name) or REPO_MAP.get(repo_name.lower())

    if not repo_path:
        os.makedirs(REPOS_DIR, exist_ok=True)
        repo_path = os.path.join(REPOS_DIR, repo_name)

        if not os.path.exists(repo_path):
            url = clone_url or f"git@github.com:{GITHUB_ORG}/{repo_name}.git"
            log(f'Repo "{repo_name}" not in REPO_MAP — auto-cloning from {url}...')
            shell(f'git clone {url} "{repo_path}"')
            log(f"Cloned to {repo_path}")

    if not os.path.exists(repo_path):
        raise RuntimeError(f"Repo path does not exist: {repo_path}")
    if not os.path.exists(os.path.join(repo_path, ".git")):
        raise RuntimeError(f"Not a git repo: {repo_path}")

    log(f"Updating {repo_name} at {repo_path}...")
    shell("git fetch origin", cwd=repo_path)
    try:
        shell(f"git rev-parse --verify origin/{TARGET_BRANCH}", cwd=repo_path)
        shell(f"git checkout {TARGET_BRANCH}", cwd=repo_path)
        shell(f"git pull origin {TARGET_BRANCH}", cwd=repo_path)
    except Exception:
        try:
            shell("git checkout main && git pull origin main", cwd=repo_path)
        except Exception:
            shell("git checkout master && git pull origin master", cwd=repo_path)

    return repo_path


def create_worktree(repo_path: str, branch_name: str) -> str:
    worktree_path = os.path.join(repo_path, ".worktrees", branch_name)
    os.makedirs(os.path.dirname(worktree_path), exist_ok=True)

    try:
        shell(f'git worktree remove "{worktree_path}" --force', cwd=repo_path)
    except Exception:
        pass
    try:
        shell(f'git branch -D "{branch_name}"', cwd=repo_path)
    except Exception:
        pass

    # Detect base branch
    base_branch = "origin/master"
    try:
        shell(f"git rev-parse --verify origin/{TARGET_BRANCH}", cwd=repo_path)
        base_branch = f"origin/{TARGET_BRANCH}"
    except Exception:
        try:
            shell("git rev-parse --verify origin/main", cwd=repo_path)
            base_branch = "origin/main"
        except Exception:
            pass

    shell(f'git worktree add -b "{branch_name}" "{worktree_path}" {base_branch}', cwd=repo_path)
    log(f"Created worktree at {worktree_path} (branch: {branch_name})")
    return worktree_path


def cleanup_worktree(repo_path: str, worktree_path: str) -> None:
    try:
        shell(f'git worktree remove "{worktree_path}" --force', cwd=repo_path)
    except Exception:
        pass


# ── Change Summary ────────────────────────────────────────────────────────

def _detect_base_ref(worktree_path: str) -> str:
    """Detect the base remote ref for the worktree branch."""
    for ref in [f"origin/{TARGET_BRANCH}", "origin/main", "origin/master"]:
        try:
            shell(f"git rev-parse --verify {ref}", cwd=worktree_path)
            return ref
        except Exception:
            continue
    return "HEAD~2"


def generate_change_summary(worktree_path: str) -> dict[str, Any]:
    """Generate a summary of changes made in the worktree (commits, diff stats, env changes)."""
    base_ref = _detect_base_ref(worktree_path)
    summary: dict[str, Any] = {
        "commit_messages": [],
        "diff_stat": "",
        "files_changed": [],
        "env_changes": [],
    }

    try:
        raw = shell(f'git log --format="%s" {base_ref}..HEAD', cwd=worktree_path)
        summary["commit_messages"] = [m for m in raw.split("\n") if m.strip()]
    except Exception:
        pass

    try:
        summary["diff_stat"] = shell(f"git diff {base_ref}..HEAD --stat", cwd=worktree_path)
    except Exception:
        pass

    try:
        raw = shell(f"git diff {base_ref}..HEAD --name-only", cwd=worktree_path)
        summary["files_changed"] = [f for f in raw.split("\n") if f.strip()]
    except Exception:
        pass

    summary["env_changes"] = _detect_env_changes(worktree_path, base_ref, summary["files_changed"])
    return summary


def _detect_env_changes(
    worktree_path: str, base_ref: str, files_changed: list[str]
) -> list[str]:
    """Detect environment-related changes (env files, new env variable references)."""
    env_changes: list[str] = []

    # Check for env-related file modifications
    env_files = [
        f for f in files_changed
        if os.path.basename(f).lower().startswith(".env")
        or "docker-compose" in os.path.basename(f).lower()
    ]
    if env_files:
        env_changes.append(
            f"**Modified env files:** {', '.join(f'`{f}`' for f in env_files)}"
        )

    # Scan diff for new env variable references
    try:
        diff = shell(f"git diff {base_ref}..HEAD", cwd=worktree_path, timeout=30)
        added_vars: set[str] = set()
        for line in diff.split("\n"):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            # Python: os.environ["KEY"], os.environ.get("KEY"), os.getenv("KEY")
            for m in re.finditer(
                r'os\.(?:environ(?:\[|\.get\s*\()|getenv\s*\()\s*["\']([A-Z_][A-Z0-9_]*)["\']',
                line,
            ):
                added_vars.add(m.group(1))
            # Node.js: process.env.KEY
            for m in re.finditer(r'process\.env\.([A-Z_][A-Z0-9_]*)', line):
                added_vars.add(m.group(1))
            # .env file lines: KEY=value
            m_env = re.match(r'^\+([A-Z][A-Z0-9_]{2,})=', line)
            if m_env:
                added_vars.add(m_env.group(1))

        if added_vars:
            env_changes.append(
                f"**New/modified env variables:** {', '.join(f'`{v}`' for v in sorted(added_vars))}"
            )
    except Exception:
        pass

    return env_changes


# ── Claude Code ──────────────────────────────────────────────────────────────

def _run_claude(identifier: str, prompt_file: str, log_file: str, worktree_path: str, phase: str) -> bool:
    """Execute a single Claude Code invocation. Pipes prompt via stdin to avoid shell arg length limits."""
    log(f"Running Claude Code ({CLAUDE_CMD}) — {phase} for {identifier}...")
    try:
        # Pipe prompt via shell to avoid OS arg length limit on large prompts
        env = {**os.environ, "PATH": f"{EXTRA_PATHS}:{os.environ.get('PATH', '')}"}
        cmd = (
            f"cat '{prompt_file}' | {CLAUDE_CMD} -p - "
            f"--allowedTools Bash Read Edit Write Glob Grep "
            f"--max-turns 30 --output-format text"
        )
        result = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True,
            cwd=worktree_path, timeout=7200, env=env,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, CLAUDE_CMD, output=result.stdout, stderr=result.stderr,
            )
        output = result.stdout.strip()
        with open(log_file, "a") as f:
            f.write(f"\n{'='*60}\n{phase}\n{'='*60}\n{output}\n")

        # Detect max-turns exhaustion — Claude returns exit 0 but work is incomplete
        if "Reached max turns" in output:
            log(f"Claude Code {phase} hit max turns for {identifier} — treating as failure")
            return False

        log(f"Claude Code {phase} finished for {identifier}")
        return True
    except subprocess.CalledProcessError as err:
        log(f"Claude Code {phase} failed for {identifier}: {err}")
        stdout = err.output or ""
        stderr = err.stderr or ""
        with open(log_file, "a") as f:
            f.write(f"\n{'='*60}\n{phase} — ERROR\n{'='*60}\n{err}\nSTDOUT: {stdout}\nSTDERR: {stderr}\n")
        return False


def run_claude_code(
    worktree_path: str, issue: dict[str, Any], repo_name: str, team_key: str
) -> bool:
    identifier = issue["identifier"]
    log_file = os.path.join(LOGS_DIR, f"claude_{identifier}_{repo_name}.log")

    # Clear log file for fresh run
    with open(log_file, "w") as f:
        f.write(f"# Claude Code log for {identifier} ({repo_name})\n")

    if not dev_skill:
        log(f"ERROR: Developer Skill not initialized for {identifier}")
        return False

    # Use developer skill for scope-aware prompt building
    log(f"Developer Skill processing {identifier} ({repo_name})...")
    try:
        result = dev_skill.process(issue, team_key, worktree_path, repo_name)
    except RuntimeError as err:
        log(f"FAILED: {identifier} ({repo_name}) — {err}")
        with open(log_file, "a") as f:
            f.write(f"\nFAILED: {err}\n")
        return False

    ctx = result.enriched_context
    pf = result.pathfinder
    pf_info = f"Pathfinder: {pf.classification}/{pf.complexity}, repos={pf.repos}" if pf else "Pathfinder: not found"
    log(
        f"Scope: {result.scope_type} | Stack: {result.stack_type} | {pf_info} | "
        f"Enriched: {len(ctx.comments)} comments, "
        f"{len(ctx.sub_issues)} sub-issues, "
        f"{len(ctx.relations)} relations, "
        f"{len(ctx.file_hints)} file hints"
    )

    # ── Agent 1: Test Agent ───────────────────────────────────────────
    log(f"[{identifier}] Starting Test Agent for {repo_name}...")
    test_prompt_file = os.path.join(LOGS_DIR, f"prompt_test_{identifier}_{repo_name}.txt")
    with open(test_prompt_file, "w") as f:
        f.write(result.test_prompt)

    test_ok = _run_claude(identifier, test_prompt_file, log_file, worktree_path, "Test Agent")
    if not test_ok:
        log(f"[{identifier}] Test Agent failed for {repo_name} — skipping implementation")
        return False
    log(f"[{identifier}] Test Agent complete for {repo_name} — tests committed.")

    # ── Agent 2: Dev Agent ────────────────────────────────────────────
    # Verify worktree still exists (Test Agent's Claude may have removed it)
    if not os.path.exists(worktree_path):
        log(f"[{identifier}] Worktree gone after Test Agent — recreating...")
        try:
            repo_path = os.path.dirname(os.path.dirname(worktree_path))  # .worktrees/claude/id -> repo
            branch_name = os.path.basename(worktree_path)
            # The branch should still exist with test commits — just re-add the worktree
            shell(f'git worktree add "{worktree_path}" "{branch_name}"', cwd=repo_path)
            log(f"[{identifier}] Worktree recreated at {worktree_path}")
        except Exception as err:
            log(f"[{identifier}] Failed to recreate worktree: {err}")
            return False

    log(f"[{identifier}] Starting Dev Agent for {repo_name}...")
    impl_prompt_file = os.path.join(LOGS_DIR, f"prompt_impl_{identifier}_{repo_name}.txt")
    with open(impl_prompt_file, "w") as f:
        f.write(result.impl_prompt)

    return _run_claude(identifier, impl_prompt_file, log_file, worktree_path, "Dev Agent")




# ── PR Creation ──────────────────────────────────────────────────────────────

def push_and_create_pr(
    worktree_path: str, repo_name: str, branch_name: str, issue: dict[str, Any],
    change_summary: dict[str, Any] | None = None,
) -> str | None:
    identifier = issue["identifier"]

    try:
        diff = shell("git diff HEAD~1 --stat", cwd=worktree_path)
        if not diff:
            log(f"No changes for {identifier}")
            return None
    except Exception:
        log(f"No commits for {identifier}")
        return None

    if os.path.exists(os.path.join(worktree_path, "CLAUDE_UNABLE.md")):
        log(f"Claude Code unable to fix {identifier}")
        return None

    log(f"Pushing {branch_name}...")
    shell(f'git push origin "{branch_name}"', cwd=worktree_path)

    remote_url = shell("git remote get-url origin", cwd=worktree_path)
    repo_match = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?$", remote_url)
    gh_repo = f"{repo_match.group(1)}/{repo_match.group(2)}" if repo_match else f"{GITHUB_ORG}/{repo_name}"
    log(f"Detected GitHub repo: {gh_repo}")

    title = issue["title"]
    description = issue.get("description") or "N/A"
    url = issue["url"]

    # Build PR body
    pr_parts = [f"## Summary"]

    # Summary from commit messages
    if change_summary and change_summary.get("commit_messages"):
        for msg in change_summary["commit_messages"]:
            pr_parts.append(f"- {msg}")
    else:
        pr_parts.append(f"{identifier}: {title}")
    pr_parts.append("")

    # Ticket link
    pr_parts.append(f"## Ticket\n[{identifier}]({url})\n")

    # Changes Made (files changed)
    if change_summary and change_summary.get("files_changed"):
        pr_parts.append("## Changes Made")
        for f in change_summary["files_changed"]:
            pr_parts.append(f"- `{f}`")
        pr_parts.append("")

        if change_summary.get("diff_stat"):
            pr_parts.append(f"```\n{change_summary['diff_stat']}\n```\n")

    # Acceptance Criteria (parsed from ticket description)
    ac = parse_acceptance_criteria(description)
    if ac:
        pr_parts.append("## Acceptance Criteria")
        for criterion in ac:
            pr_parts.append(f"- [ ] {criterion}")
        pr_parts.append("")

    # Environment Changes
    if change_summary and change_summary.get("env_changes"):
        pr_parts.append("## \u26a0\ufe0f Environment Changes")
        for change in change_summary["env_changes"]:
            pr_parts.append(change)
        pr_parts.append("")

    pr_parts.append("---\n*Automated by NightShift*")
    pr_body = "\n".join(pr_parts)

    pr_body_file = os.path.join(LOGS_DIR, f"pr_body_{identifier}.txt")
    with open(pr_body_file, "w") as f:
        f.write(pr_body)

    pr_title = f"{identifier}: {title}"

    # Create PR via gh CLI
    try:
        pr_url = shell(
            f'gh pr create --repo "{gh_repo}" --base "{TARGET_BRANCH}" '
            f'--head "{branch_name}" --title "{pr_title}" '
            f'--body-file "{pr_body_file}"',
            cwd=worktree_path,
        )
        return pr_url
    except Exception as err:
        log(f"gh pr create failed for {identifier} on {gh_repo}: {err}")
        fallback_url = f"https://github.com/{gh_repo}/compare/{TARGET_BRANCH}...{branch_name}?expand=1"
        log(f"Branch pushed but PR creation failed. Manual URL: {fallback_url}")
        return None


# ── Linear Updates ───────────────────────────────────────────────────────────

def transition_issue(issue: dict[str, Any], state_type: str, state_name: str | None = None) -> None:
    """Transition issue to a target state. Matches by name first (if provided), then by type."""
    try:
        team_id = (issue.get("team") or {}).get("id") or linear.get_issue_team_id(issue["id"])
        if not team_id:
            return
        states = linear.get_team_states(team_id)
        target_state = None
        if state_name:
            target_state = next((s for s in states if s["name"].lower() == state_name.lower()), None)
        if not target_state:
            target_state = next((s for s in states if s["type"] == state_type), None)
        if target_state:
            linear.update_issue(issue["id"], target_state["id"])
            log(f'Moved {issue["identifier"]} to "{target_state["name"]}"')
        else:
            log(f'No state matching name="{state_name}" or type="{state_type}" found for team')
    except Exception as err:
        log(f'Failed to transition {issue["identifier"]}: {err}')


def comment_on_issue(issue_id: str, body: str) -> None:
    try:
        linear.create_comment(issue_id, body)
    except Exception as err:
        log(f"Comment failed: {err}")


# ── Per-Repo Processor (runs in thread) ───────────────────────────────────────

def _process_repo(
    entry: RepoEntry, issue: dict[str, Any], team_key: str, identifier: str,
) -> tuple[str | None, tuple[str, dict[str, Any]] | None]:
    """Process one repo for a ticket. Returns (pr_url, (repo_name, summary)) or (None, None)."""
    log(f"  [{identifier}] Working on repo: {entry.name}")
    try:
        # Per-repo lock: prevents concurrent clone/fetch on the same repo
        with _get_repo_lock(entry.name):
            repo_path = get_repo_path(entry.name, entry.clone_url)
            branch_name = f"claude/{identifier.lower()}"
            worktree_path = create_worktree(repo_path, branch_name)

        # Claude Code and PR creation run outside the repo lock
        # (worktrees are fully isolated)
        success = run_claude_code(worktree_path, issue, entry.name, team_key)

        if success:
            change_summary = generate_change_summary(worktree_path)
            pr_url = push_and_create_pr(
                worktree_path, entry.name, branch_name, issue, change_summary,
            )
            cleanup_worktree(repo_path, worktree_path)
            if pr_url:
                return pr_url, (entry.name, change_summary)
        else:
            cleanup_worktree(repo_path, worktree_path)
    except Exception as err:
        log(f"  [{identifier}] Error on repo {entry.name}: {err}")

    return None, None


# ── Single Issue Processor (runs in thread) ──────────────────────────────────

def _process_single_issue(issue: dict[str, Any], team_key: str, repo_entries: list[RepoEntry] | None = None) -> None:
    """Process one ticket end-to-end. Thread-safe — uses per-repo locks."""
    identifier = issue["identifier"]
    priority_name = PRIORITY_NAMES.get(issue.get("priority", 0), "None")

    labels = [l["name"] for l in (issue.get("labels") or {}).get("nodes", [])]

    log(f"\n[{priority_name}] Processing: {identifier} - {issue['title']}")
    log(f"Labels: {', '.join(labels) or 'none'}")

    # Use pre-detected repos from Phase 2 (includes Pathfinder), or fallback
    if not repo_entries:
        project_name = (issue.get("project") or {}).get("name")
        repo_entries = detect_repos(issue, labels, team_key, project_name)
    log(f"Repos: {', '.join(r.clone_url or f'{GITHUB_ORG}/{r.name}' for r in repo_entries)}")

    # Skip repos that already succeeded in a previous run
    issue_id = issue["id"]
    already_done = set(completed_repos.get(issue_id, []))
    if already_done:
        original_count = len(repo_entries)
        repo_entries = [e for e in repo_entries if e.name not in already_done]
        log(f"  [{identifier}] Skipping {original_count - len(repo_entries)} already-completed repo(s): {', '.join(already_done)}")
        if not repo_entries:
            log(f"  [{identifier}] All repos already completed — marking as done")
            with _processed_lock:
                processed_issues.add(issue_id)
            save_processed()
            return

    try:
        transition_issue(issue, "started", state_name="In Development")
        pr_urls: list[str] = []
        repo_summaries: list[tuple[str, dict[str, Any]]] = []

        # Process repos in parallel — worktrees are fully isolated
        max_workers = min(len(repo_entries), MAX_CONCURRENT_REPOS)
        failed_repos: list[str] = []
        log(f"  [{identifier}] Processing {len(repo_entries)} repo(s) with {max_workers} worker(s)...")

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_process_repo, entry, issue, team_key, identifier): entry.name
                for entry in repo_entries
            }
            for future in as_completed(futures):
                repo_name = futures[future]
                try:
                    pr_url, repo_summary = future.result()
                    if pr_url:
                        pr_urls.append(pr_url)
                    if repo_summary:
                        repo_summaries.append(repo_summary)
                    if not pr_url:
                        failed_repos.append(repo_name)
                except Exception as err:
                    log(f"  [{identifier}] Error on repo {repo_name}: {err}")
                    failed_repos.append(repo_name)

        if pr_urls:
            if failed_repos:
                log(f"  [{identifier}] Partial success — {len(failed_repos)} repo(s) failed: {', '.join(failed_repos)}")

            # Build ticket comment
            branch_name = f"claude/{identifier.lower()}"
            comment_parts = []

            if failed_repos:
                comment_parts.append(
                    f"Partial completion. {len(pr_urls)} PR(s) created, "
                    f"{len(failed_repos)} repo(s) failed: {', '.join(f'`{r}`' for r in failed_repos)}\n"
                )
            else:
                comment_parts.append("Development complete. Branch and PR created automatically.\n")

            # Branch and PR info
            for i, url in enumerate(pr_urls):
                repo_label = repo_summaries[i][0] if i < len(repo_summaries) else ""
                if len(pr_urls) > 1 and repo_label:
                    comment_parts.append(f"**Branch ({repo_label}):** `{branch_name}`")
                    comment_parts.append(f"**PR ({repo_label}):** {url}")
                else:
                    comment_parts.append(f"**Branch:** `{branch_name}`")
                    comment_parts.append(f"**PR:** {url}")

            # Add changes summary per repo
            for repo_name, summary in repo_summaries:
                if summary.get("commit_messages"):
                    header = "### Changes Summary" if len(repo_summaries) == 1 else f"### Changes Summary ({repo_name})"
                    comment_parts.append(f"\n{header}")
                    for msg in summary["commit_messages"]:
                        comment_parts.append(f"- {msg}")

                if summary.get("files_changed"):
                    comment_parts.append("\n**Files changed:**")
                    for f in summary["files_changed"]:
                        comment_parts.append(f"- `{f}`")

                if summary.get("diff_stat"):
                    comment_parts.append(f"\n```\n{summary['diff_stat']}\n```")

            # Add env changes if any
            all_env_changes: list[str] = []
            for _, summary in repo_summaries:
                all_env_changes.extend(summary.get("env_changes", []))
            if all_env_changes:
                comment_parts.append("\n### \u26a0\ufe0f Environment Changes")
                for change in all_env_changes:
                    comment_parts.append(change)

            if failed_repos:
                comment_parts.append(f"\nTicket NOT marked as done — {len(failed_repos)} repo(s) need retry.")
            else:
                comment_parts.append("\nChanges were committed and pushed. The ticket has been moved to Code Review.")
            comment_on_issue(issue["id"], "\n".join(comment_parts))

            log(f"Done: {identifier} -> {', '.join(pr_urls)}")

            # Track which repos succeeded (for smart retry)
            succeeded_repos = [name for name, _ in repo_summaries]
            if succeeded_repos:
                with _processed_lock:
                    prev = completed_repos.get(issue_id, [])
                    completed_repos[issue_id] = list(set(prev + succeeded_repos))
                save_completed_repos()

            # Mark as fully processed only if ALL repos succeeded (including previously completed ones)
            all_done = set(completed_repos.get(issue_id, []))
            if not failed_repos:
                transition_issue(issue, "started", state_name="Code Review")
                with _processed_lock:
                    processed_issues.add(issue_id)
                save_processed()
                log(f"  [{identifier}] All repos done — marked as processed")
            else:
                # Move back to Ready for Development so next scan retries the failed repos
                transition_issue(issue, "started", state_name="Ready for Development")
                log(f"  [{identifier}] Moved back to Ready for Development — will retry {', '.join(failed_repos)} next run")
        else:
            # Move back to Ready for Development so next scan retries
            transition_issue(issue, "started", state_name="Ready for Development")
            log(f"No PRs created for {identifier} — moved back to Ready for Development")
    except Exception as err:
        # Move back to Ready for Development on unexpected errors
        try:
            transition_issue(issue, "started", state_name="Ready for Development")
        except Exception:
            pass
        log(f"Error: {identifier}: {err} — moved back to Ready for Development")


# ── Main Processing Loop (3-phase) ──────────────────────────────────────────

def process_tickets() -> None:
    global dev_skill
    log("=== Starting ticket scan ===")
    log(f"Max concurrent tickets: {MAX_CONCURRENT_TICKETS}")
    try:
        me = linear.get_viewer()
        log(f'Authenticated as: {me["name"]} ({me["email"]})')

        # Initialize developer skill with viewer ID and Sentinel path
        dev_skill = DeveloperSkill(
            LINEAR_API_KEY, me["id"], GITHUB_ORG,
            sentinel_skills_path=SENTINEL_SKILLS_PATH,
        )
        if not dev_skill.sentinel_available:
            log("ERROR: Sentinel Guardian skills not found! Tickets will NOT be processed.")
            log(f"  Expected path: {SENTINEL_SKILLS_PATH}")
            log("  Ensure skills are mounted in Docker or exist at the configured path.")
        else:
            available_skills = dev_skill.sentinel.get_available_skills()
            log(f"Sentinel Guardian: enabled ({len(available_skills)} skills available)")

        teams = linear.get_teams()

        # ── Phase 1: COLLECT — fetch all eligible issues, sorted by priority ──

        eligible: list[tuple[dict[str, Any], str]] = []  # (issue, team_key)

        for team in teams:
            log(f'Scanning team: {team["name"]} ({team["key"]})')
            issues = linear.get_issues_with_labels(team["id"], me["id"], first=20)

            for issue in issues:
                if issue["id"] in processed_issues:
                    continue

                labels_lower = [l["name"].lower() for l in (issue.get("labels") or {}).get("nodes", [])]
                if PROCESSING_LABEL in labels_lower or DONE_LABEL in labels_lower:
                    continue

                eligible.append((issue, team["key"]))

        if not eligible:
            log("No eligible tickets found.")
            log("=== Scan complete ===")
            return

        # Sort by priority: Urgent (1) > High (2) > Medium (3) > Low (4) > None (0)
        eligible.sort(key=lambda x: _priority_sort_key(x[0]))

        priority_summary = ", ".join(
            f"{issue['identifier']}({PRIORITY_NAMES.get(issue.get('priority', 0), 'None')})"
            for issue, _ in eligible
        )
        log(f"Eligible tickets ({len(eligible)}), priority order: {priority_summary}")

        # ── Phase 2: PREPARE — detect repos (with Pathfinder) and clone in parallel ──

        from skills.pathfinder_parser import parse_pathfinder_comment, PathfinderAnalysis
        from skills.repo_filter import filter_repos

        all_repo_entries: dict[str, RepoEntry] = {}  # repo_name -> entry (deduplicated)
        issue_repos: list[tuple[dict[str, Any], str, list[RepoEntry]]] = []

        for issue, team_key in eligible:
            labels = [l["name"] for l in (issue.get("labels") or {}).get("nodes", [])]
            project_name = (issue.get("project") or {}).get("name")

            # Try Pathfinder comment first for repo detection
            entries: list[RepoEntry] = []
            pf: PathfinderAnalysis | None = None
            try:
                comments = linear.get_issue_comments(issue["id"])
                pf = parse_pathfinder_comment(comments)
                if pf and pf.repos:
                    log(f"  [{issue['identifier']}] Pathfinder repos (raw): {pf.repos}")

                    # LLM pre-analysis: filter out repos that need no changes
                    filtered_names = filter_repos(pf.full_comment, pf.repos)

                    entries = [
                        RepoEntry(name=r, clone_url=f"git@github.com:{GITHUB_ORG}/{r}.git")
                        for r in filtered_names
                    ]
                    log(f"  [{issue['identifier']}] Pathfinder repos (filtered): {filtered_names}")
            except Exception:
                pass

            # Fallback to standard detection
            if not entries:
                entries = detect_repos(issue, labels, team_key, project_name)

            # ── Decompose complex tickets (L/XL) into subtasks ──
            if should_decompose(pf, issue, linear):
                team_id = (issue.get("team") or {}).get("id") or linear.get_issue_team_id(issue["id"])
                if team_id:
                    created_subtasks = decompose_and_create_subtasks(
                        issue, pf, linear, team_id, me["id"],
                    )
                    if created_subtasks:
                        # Move parent to "In Progress" — subtasks will be processed individually
                        transition_issue(issue, "started", state_name="In Development")
                        log(f"  [{issue['identifier']}] Decomposed into {len(created_subtasks)} subtasks — processing subtasks instead")

                        # Fetch all team issues once (to find full subtask data)
                        all_team_issues: list[dict[str, Any]] = []
                        try:
                            all_team_issues = linear.get_issues_with_labels(team_id, me["id"], first=50)
                        except Exception:
                            pass
                        sub_lookup = {i["id"]: i for i in all_team_issues}

                        # Replace parent with its subtasks in the processing queue
                        for sub in created_subtasks:
                            sub_issue = sub_lookup.get(sub["id"])
                            if not sub_issue:
                                # Build minimal issue dict from creation response
                                sub_issue = {
                                    "id": sub["id"],
                                    "identifier": sub["identifier"],
                                    "title": sub["title"],
                                    "description": "",
                                    "url": sub.get("url", issue["url"]),
                                    "priority": issue.get("priority", 0),
                                    "labels": {"nodes": []},
                                    "project": issue.get("project"),
                                    "team": issue.get("team") or {"id": team_id},
                                    "state": sub.get("state", {"name": "Backlog", "type": "unstarted"}),
                                }
                            issue_repos.append((sub_issue, team_key, entries))
                            for entry in entries:
                                if entry.name.lower() not in all_repo_entries:
                                    all_repo_entries[entry.name.lower()] = entry

                        # Mark parent as processed so we don't re-pick it up
                        with _processed_lock:
                            processed_issues.add(issue["id"])
                        save_processed()
                        continue  # Skip adding the parent to issue_repos

            issue_repos.append((issue, team_key, entries))
            for entry in entries:
                if entry.name.lower() not in all_repo_entries:
                    all_repo_entries[entry.name.lower()] = entry

        if all_repo_entries:
            unique_repos = list(all_repo_entries.values())
            log(f"Preparing {len(unique_repos)} unique repo(s): {', '.join(r.name for r in unique_repos)}")

            def _prepare_repo(entry: RepoEntry) -> None:
                try:
                    with _get_repo_lock(entry.name):
                        get_repo_path(entry.name, entry.clone_url)
                except Exception as err:
                    log(f"Failed to prepare repo {entry.name}: {err}")

            with ThreadPoolExecutor(max_workers=min(len(unique_repos), 4)) as pool:
                list(pool.map(_prepare_repo, unique_repos))

            log("Repos ready.")

        # ── Phase 3: EXECUTE — process tickets in parallel ──

        log(f"Processing {len(eligible)} ticket(s) with {MAX_CONCURRENT_TICKETS} worker(s)...")

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TICKETS) as pool:
            futures = {
                pool.submit(_process_single_issue, issue, team_key, entries): issue["identifier"]
                for issue, team_key, entries in issue_repos
            }
            for future in as_completed(futures):
                identifier = futures[future]
                try:
                    future.result()
                except Exception as err:
                    log(f"Unhandled error processing {identifier}: {err}")

    except Exception as err:
        log(f"Scan error: {err}")
    log("=== Scan complete ===")
