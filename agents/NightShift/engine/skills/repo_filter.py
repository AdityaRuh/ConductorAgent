"""
Repo Filter — LLM-based pre-analysis to skip repos that need no changes.

Before spawning expensive Test Agent + Dev Agent sessions for every repo listed
in a Pathfinder comment, this module makes a lightweight Claude CLI call to
determine which repos actually need code changes.

Usage:
    from skills.repo_filter import filter_repos

    filtered = filter_repos(pathfinder_comment, ["repo-a", "repo-b", "repo-c"])
    # Returns only repos that actually need modifications
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from lib.config import CLAUDE_CMD, LOGS_DIR
from lib.core import log, EXTRA_PATHS


_FILTER_PROMPT_TEMPLATE = """\
You are a code change analyst. Given the following Pathfinder analysis for a \
software ticket, determine which repositories actually need code changes.

A repo needs changes if the analysis says it requires modifications, new code, \
bug fixes, config changes, or any hands-on development work.

A repo does NOT need changes if the analysis says things like:
- "No Changes Needed"
- "No modifications required"
- "Already handles this correctly"
- "Pass-through proxy, no changes"
- "No action required"
- The repo is only mentioned for context/reference but has no action items

<pathfinder_analysis>
{analysis_text}
</pathfinder_analysis>

<repos_to_evaluate>
{repo_list}
</repos_to_evaluate>

Return ONLY the repo names that need code changes, one per line. \
No explanations, no bullet points, no numbering — just bare repo names. \
If none need changes, return the word NONE."""


def filter_repos(
    analysis_text: str,
    repo_names: list[str],
) -> list[str]:
    """
    Use a lightweight Claude CLI call to determine which repos need changes.

    Args:
        analysis_text: Full Pathfinder comment body (RCA/TRD).
        repo_names: List of repo names detected from the analysis.

    Returns:
        Filtered list of repo names that actually need code changes.
        Falls back to the full list if the LLM call fails.
    """
    if not repo_names:
        return []

    if len(repo_names) == 1:
        log(f"Repo filter: only 1 repo ({repo_names[0]}), skipping filter")
        return repo_names

    prompt = _FILTER_PROMPT_TEMPLATE.format(
        analysis_text=analysis_text,
        repo_list="\n".join(repo_names),
    )

    try:
        filtered = _call_claude_filter(prompt, repo_names)
        if filtered is not None:
            removed = set(repo_names) - set(filtered)
            if removed:
                log(f"Repo filter: keeping {filtered}, filtered out {sorted(removed)}")
            else:
                log(f"Repo filter: all repos need changes — {repo_names}")
            return filtered
    except Exception as err:
        log(f"Repo filter: LLM call failed ({err}), using all repos as fallback")

    return repo_names


def _call_claude_filter(prompt: str, original_repos: list[str]) -> list[str] | None:
    """
    Execute a Claude CLI call in --print mode to filter repos.

    Returns filtered list, or None if the call fails or produces unusable output.
    """
    # Write prompt to temp file to avoid shell arg length issues
    prompt_file = os.path.join(LOGS_DIR, "prompt_repo_filter.txt")
    with open(prompt_file, "w") as f:
        f.write(prompt)

    env = {**os.environ, "PATH": f"{EXTRA_PATHS}:{os.environ.get('PATH', '')}"}
    cmd = f"cat '{prompt_file}' | {CLAUDE_CMD} --print -p - --max-turns 2"

    log(f"Repo filter: calling Claude CLI to evaluate {len(original_repos)} repos...")
    result = subprocess.run(
        cmd, shell=True,
        capture_output=True, text=True,
        timeout=30, env=env,
    )

    if result.returncode != 0:
        log(f"Repo filter: Claude CLI returned non-zero ({result.returncode})")
        return None

    output = result.stdout.strip()
    if not output:
        log("Repo filter: empty response from Claude CLI")
        return None

    # Parse response
    return _parse_filter_response(output, original_repos)


def _parse_filter_response(output: str, original_repos: list[str]) -> list[str] | None:
    """Parse the Claude CLI response into a filtered repo list."""
    # Check for explicit "none need changes"
    if output.strip().upper() == "NONE":
        log("Repo filter: LLM says no repos need changes — falling back to all repos for safety")
        return original_repos

    # Build a lowercase lookup for matching
    repo_lookup = {r.lower(): r for r in original_repos}

    filtered: list[str] = []
    for line in output.strip().split("\n"):
        candidate = line.strip().strip("-").strip("*").strip("`").strip()
        if not candidate:
            continue
        # Match against known repo names (case-insensitive)
        if candidate.lower() in repo_lookup:
            repo_name = repo_lookup[candidate.lower()]
            if repo_name not in filtered:
                filtered.append(repo_name)

    if not filtered:
        log(f"Repo filter: could not parse any known repos from response: {output[:200]}")
        return None

    # Sanity check — don't filter out everything
    if len(filtered) == 0:
        log("Repo filter: would filter all repos — falling back to full list")
        return original_repos

    return filtered
