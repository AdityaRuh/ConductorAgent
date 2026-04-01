"""
Task Decomposer — breaks complex (L/XL) tickets into subtasks.

When Pathfinder marks a ticket as L or XL complexity and it has no existing
children, this module uses Claude CLI to analyze the Pathfinder analysis and
produce a set of focused subtasks. Each subtask gets its own Claude Code
session (30 turns), avoiding the max-turns/timeout failures that happen when
a single session tries to tackle a massive change.

Flow:
  1. Check if decomposition is needed (complexity L/XL, no existing children)
  2. Call Claude CLI to propose subtask breakdowns from Pathfinder analysis
  3. Create subtasks in Linear as children of the parent ticket
  4. Return the created subtasks so the pipeline can process them individually

Usage:
    from skills.task_decomposer import should_decompose, decompose_and_create_subtasks

    if should_decompose(pathfinder, issue, linear_client):
        subtasks = decompose_and_create_subtasks(
            issue, pathfinder, enriched_context,
            linear_client, team_id, viewer_id,
        )
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any

from lib.config import CLAUDE_CMD, LOGS_DIR
from lib.linear_client import LinearClient
from skills.pathfinder_parser import PathfinderAnalysis


# Complexity levels that trigger decomposition
DECOMPOSE_COMPLEXITIES = {"L", "XL"}

# Limits
MAX_SUBTASKS = 7
MIN_SUBTASKS = 2


@dataclass
class SubTaskDefinition:
    """A proposed subtask before it's created in Linear."""
    title: str
    description: str
    priority: int  # inherits from parent


def _log(msg: str) -> None:
    """Import-safe logging — avoids circular import with core.py."""
    try:
        from lib.core import log
        log(msg)
    except ImportError:
        from datetime import datetime
        print(f"[{datetime.utcnow().isoformat()}Z] {msg}", flush=True)


# ── Gate: should we decompose? ───────────────────────────────────────────


def should_decompose(
    pathfinder: PathfinderAnalysis | None,
    issue: dict[str, Any],
    client: LinearClient,
) -> bool:
    """
    Determine if a ticket should be decomposed into subtasks.

    Returns True when:
      - Pathfinder analysis exists AND complexity is L or XL
      - The ticket has NO existing children (to avoid re-decomposing)
    """
    if not pathfinder:
        return False

    if pathfinder.complexity not in DECOMPOSE_COMPLEXITIES:
        return False

    # Check if ticket already has children — don't decompose twice
    try:
        children = client.get_issue_children(issue["id"], first=1)
        if children:
            _log(f"  [{issue['identifier']}] Already has {len(children)}+ subtask(s) — skipping decomposition")
            return False
    except Exception:
        pass

    _log(f"  [{issue['identifier']}] Complexity={pathfinder.complexity} — will decompose into subtasks")
    return True


# ── Decomposition via Claude CLI ─────────────────────────────────────────

_DECOMPOSE_PROMPT = """\
You are a senior software architect. A development ticket has been analyzed by \
Pathfinder and marked as **{complexity}** complexity. It's too large for a single \
development session to handle, so you need to break it into smaller, independently \
implementable subtasks.

## Parent Ticket
**{identifier}**: {title}

### Description
{description}

### Pathfinder Analysis
{pathfinder_text}

## Rules for Subtask Decomposition

1. Each subtask must be **independently implementable and testable** — no subtask \
should depend on another being completed first unless absolutely necessary.
2. Each subtask should be scoped to **one logical unit of work** (e.g., one module, \
one API endpoint, one component, one service layer change).
3. Aim for **{min_tasks}-{max_tasks} subtasks**. Fewer is better if the work is \
naturally grouped.
4. If the Pathfinder analysis has a "Code Changes" table, use it as the primary \
guide for grouping. Changes to the same file/module usually belong together.
5. If the Pathfinder specifies an "Implementation Order", respect dependencies — \
foundational changes (models, schemas, configs) should be in earlier subtasks.
6. Each subtask title should be clear and actionable (start with a verb).
7. Each subtask description should include:
   - What specific files/functions to modify (from Pathfinder)
   - What the expected behavior change is
   - Any relevant acceptance criteria from the parent ticket

## Output Format

Return a JSON array of subtask objects. Each object has:
- "title": string (concise, actionable title)
- "description": string (markdown description with specific files and scope)

Return ONLY the JSON array, no other text. Example:
```json
[
  {{
    "title": "Add validation schema for user registration endpoint",
    "description": "## Scope\\n- Modify `src/validators/user.py` ..."
  }},
  {{
    "title": "Update user service to enforce new validation rules",
    "description": "## Scope\\n- Modify `src/services/user_service.py` ..."
  }}
]
```"""


def _build_decompose_prompt(
    issue: dict[str, Any],
    pathfinder: PathfinderAnalysis,
    description: str,
) -> str:
    """Build the prompt for Claude CLI to decompose the task."""
    return _DECOMPOSE_PROMPT.format(
        complexity=pathfinder.complexity,
        identifier=issue["identifier"],
        title=issue["title"],
        description=description or "(no description)",
        pathfinder_text=pathfinder.full_comment,
        min_tasks=MIN_SUBTASKS,
        max_tasks=MAX_SUBTASKS,
    )


def _call_claude_decompose(prompt: str, identifier: str) -> list[SubTaskDefinition] | None:
    """Call Claude CLI to propose subtask breakdowns."""
    from lib.core import EXTRA_PATHS

    os.makedirs(LOGS_DIR, exist_ok=True)
    prompt_file = os.path.join(LOGS_DIR, f"prompt_decompose_{identifier}.txt")
    with open(prompt_file, "w") as f:
        f.write(prompt)

    env = {**os.environ, "PATH": f"{EXTRA_PATHS}:{os.environ.get('PATH', '')}"}
    cmd = f"cat '{prompt_file}' | {CLAUDE_CMD} --print -p - --max-turns 3"

    _log(f"  [{identifier}] Calling Claude CLI for task decomposition...")
    try:
        result = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True,
            timeout=60, env=env,
        )
    except subprocess.TimeoutExpired:
        _log(f"  [{identifier}] Claude CLI decomposition timed out (60s)")
        return None
    except Exception as err:
        _log(f"  [{identifier}] Claude CLI decomposition error: {err}")
        return None

    if result.returncode != 0:
        _log(f"  [{identifier}] Claude CLI decomposition failed (exit {result.returncode})")
        return None

    output = result.stdout.strip()
    if not output:
        _log(f"  [{identifier}] Empty response from Claude CLI decomposition")
        return None

    # Save raw output for debugging
    output_file = os.path.join(LOGS_DIR, f"decompose_output_{identifier}.txt")
    with open(output_file, "w") as f:
        f.write(output)

    return _parse_decompose_response(output, identifier)


def _parse_decompose_response(output: str, identifier: str) -> list[SubTaskDefinition] | None:
    """Parse Claude CLI response into subtask definitions."""
    # Extract JSON array from response (may be wrapped in markdown code block)
    json_match = re.search(r'\[[\s\S]*\]', output)
    if not json_match:
        _log(f"  [{identifier}] Could not find JSON array in decomposition response")
        return None

    try:
        raw = json.loads(json_match.group(0))
    except json.JSONDecodeError as err:
        _log(f"  [{identifier}] Failed to parse decomposition JSON: {err}")
        return None

    if not isinstance(raw, list) or len(raw) < MIN_SUBTASKS:
        _log(f"  [{identifier}] Decomposition returned {len(raw) if isinstance(raw, list) else 0} subtasks (min {MIN_SUBTASKS})")
        return None

    subtasks: list[SubTaskDefinition] = []
    for item in raw[:MAX_SUBTASKS]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        description = (item.get("description") or "").strip()
        if title:
            subtasks.append(SubTaskDefinition(
                title=title,
                description=description,
                priority=0,  # will be set from parent
            ))

    if len(subtasks) < MIN_SUBTASKS:
        _log(f"  [{identifier}] Only {len(subtasks)} valid subtasks parsed (min {MIN_SUBTASKS})")
        return None

    _log(f"  [{identifier}] Decomposed into {len(subtasks)} subtasks")
    return subtasks


# ── Create subtasks in Linear ────────────────────────────────────────────


def _transition_to_ready(client: LinearClient, issue: dict[str, Any], team_id: str) -> None:
    """Transition a newly created subtask to 'Ready for Development' state."""
    states = client.get_team_states(team_id)
    # Try exact name match first, then fall back to unstarted type
    target = next((s for s in states if s["name"].lower() == "ready for development"), None)
    if not target:
        target = next((s for s in states if s["type"] == "unstarted"), None)
    if target:
        client.update_issue(issue["id"], target["id"])


def decompose_and_create_subtasks(
    issue: dict[str, Any],
    pathfinder: PathfinderAnalysis,
    client: LinearClient,
    team_id: str,
    viewer_id: str,
) -> list[dict[str, Any]]:
    """
    Decompose a complex ticket and create subtasks in Linear.

    Returns:
        List of created subtask issue dicts (with id, identifier, title, url, state).
        Empty list if decomposition fails (caller should process parent as-is).
    """
    identifier = issue["identifier"]
    description = issue.get("description") or ""
    priority = issue.get("priority", 0)

    # Step 1: Generate subtask definitions via Claude
    prompt = _build_decompose_prompt(issue, pathfinder, description)
    subtask_defs = _call_claude_decompose(prompt, identifier)

    if not subtask_defs:
        _log(f"  [{identifier}] Decomposition failed — will process as single task")
        return []

    # Step 2: Create subtasks in Linear and transition to "Ready for Development"
    created: list[dict[str, Any]] = []
    for i, sub_def in enumerate(subtask_defs, 1):
        try:
            sub_title = f"[{i}/{len(subtask_defs)}] {sub_def.title}"
            sub_desc = (
                f"**Parent ticket:** {identifier} — {issue['title']}\n\n"
                f"{sub_def.description}\n\n"
                f"---\n"
                f"*Subtask {i}/{len(subtask_defs)} — auto-decomposed from {identifier} by NightShift*"
            )

            created_issue = client.create_sub_issue(
                parent_id=issue["id"],
                team_id=team_id,
                title=sub_title,
                description=sub_desc,
                assignee_id=viewer_id,
                priority=priority,
            )
            created.append(created_issue)
            _log(f"  [{identifier}] Created subtask: {created_issue['identifier']} — {sub_title}")

            # Transition subtask to "Ready for Development" so it's eligible for processing
            # (new Linear issues default to Backlog/Triage which NightShift skips)
            try:
                _transition_to_ready(client, created_issue, team_id)
            except Exception:
                pass  # non-critical — subtask still exists, can be moved manually

        except Exception as err:
            _log(f"  [{identifier}] Failed to create subtask '{sub_def.title}': {err}")

    if created:
        # Comment on parent ticket about decomposition
        subtask_list = "\n".join(
            f"- **{s['identifier']}**: {s['title']}" for s in created
        )
        comment = (
            f"This ticket was automatically decomposed into **{len(created)} subtasks** "
            f"due to its complexity ({pathfinder.complexity}).\n\n"
            f"### Subtasks\n{subtask_list}\n\n"
            f"Each subtask will be processed individually with its own test + implementation cycle.\n\n"
            f"---\n*Decomposed by NightShift*"
        )
        try:
            client.create_comment(issue["id"], comment)
        except Exception:
            pass

        _log(f"  [{identifier}] Created {len(created)}/{len(subtask_defs)} subtasks in Linear")
    else:
        _log(f"  [{identifier}] All subtask creations failed — will process as single task")

    return created
