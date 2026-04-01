"""
core/linear_client.py
Queries Linear for tickets in the configured target statuses across all teams
listed in config/boards.yaml.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

logger = logging.getLogger(__name__)

_BOARDS_CONFIG = Path(__file__).parent.parent / "config" / "boards.yaml"

LINEAR_API_URL = "https://api.linear.app/graphql"


def _load_config() -> dict:
    with open(_BOARDS_CONFIG) as f:
        return yaml.safe_load(f)


@dataclass
class LinearTicket:
    id: str
    key: str  # e.g., "RUH-123"
    summary: str
    status: str
    issue_type: str  # Linear uses labels, but we'll use "Issue" as default
    assignee: Optional[str]
    parent_key: Optional[str]
    subtasks: List["LinearTicket"] = field(default_factory=list)


@dataclass
class TargetStatus:
    """Represents a target status with name."""
    name: str


@dataclass
class MergedTransition:
    """Represents a transition to apply to already-merged tickets."""
    name: str
    ids: dict  # team -> status name mapping


class LinearClient:
    def __init__(self, release_target: str = "qa") -> None:
        """
        Initialize LinearClient for a specific release target.
        
        Args:
            release_target: Either "qa" or "prod" — determines which statuses to query.
        """
        self._api_key = os.environ["LINEAR_API_KEY"]
        self._headers = {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
        }
        
        cfg = _load_config()
        linear_cfg = cfg.get("linear", {})
        releases = cfg.get("releases", {})
        
        self._release_target = release_target
        self._teams: List[str] = linear_cfg.get("teams", [])
        
        # Load target statuses from the selected release profile
        release_cfg = releases.get(release_target, {})
        self._release_name = release_cfg.get("name", release_target.upper())
        self._target_statuses: List[TargetStatus] = self._parse_target_statuses(release_cfg)
        self._merged_transition: Optional[MergedTransition] = self._parse_merged_transition(release_cfg)
        
        # Cache team ID mappings
        self._team_ids: Dict[str, str] = {}
        self._team_keys: Dict[str, str] = {}  # id -> key
        self._status_ids: Dict[str, Dict[str, str]] = {}  # team_id -> {status_name: status_id}
        
        if not self._target_statuses:
            logger.warning("No target_statuses found for release target '%s'", release_target)

    def _parse_target_statuses(self, release_cfg: dict) -> List[TargetStatus]:
        """Parse target_statuses from release config."""
        statuses = []
        for s in release_cfg.get("target_statuses", []):
            name = s.get("name") if isinstance(s, dict) else s
            statuses.append(TargetStatus(name=name))
        return statuses

    def _parse_merged_transition(self, release_cfg: dict) -> Optional[MergedTransition]:
        """Parse merged_transition from release config."""
        mt = release_cfg.get("merged_transition")
        if not mt:
            return None
        return MergedTransition(
            name=mt.get("name", ""),
            ids=mt.get("ids", {})
        )

    def _graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against Linear API."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        resp = requests.post(LINEAR_API_URL, json=payload, headers=self._headers)
        resp.raise_for_status()
        
        data = resp.json()
        if "errors" in data:
            logger.error("GraphQL errors: %s", data["errors"])
            raise Exception(f"GraphQL error: {data['errors']}")
        
        return data.get("data", {})

    def _ensure_team_cache(self) -> None:
        """Fetch and cache team IDs if not already cached."""
        if self._team_ids:
            return
        
        query = """
        query Teams {
            teams {
                nodes {
                    id
                    key
                    name
                }
            }
        }
        """
        data = self._graphql(query)
        for team in data.get("teams", {}).get("nodes", []):
            key = team["key"]
            team_id = team["id"]
            self._team_ids[key] = team_id
            self._team_keys[team_id] = key
            logger.debug("Cached team: %s -> %s", key, team_id)

    def _ensure_status_cache(self, team_id: str) -> None:
        """Fetch and cache workflow states for a team."""
        if team_id in self._status_ids:
            return
        
        query = """
        query WorkflowStates($teamId: String!) {
            workflowStates(filter: { team: { id: { eq: $teamId } } }) {
                nodes {
                    id
                    name
                    type
                }
            }
        }
        """
        data = self._graphql(query, {"teamId": team_id})
        self._status_ids[team_id] = {}
        for state in data.get("workflowStates", {}).get("nodes", []):
            self._status_ids[team_id][state["name"].upper()] = state["id"]
            logger.debug("Cached status for team %s: %s -> %s", team_id, state["name"], state["id"])

    def _get_target_status_names(self) -> List[str]:
        """Get all target status names (normalized to uppercase for matching)."""
        return [ts.name.upper() for ts in self._target_statuses]

    def get_ready_tickets(self) -> List[LinearTicket]:
        """Return flat list of tickets + matching subtasks across all teams."""
        if not self._teams:
            logger.warning("No teams configured in config/boards.yaml")
            return []
        if not self._target_statuses:
            logger.warning("No target_statuses configured for release target '%s'", self._release_target)
            return []

        self._ensure_team_cache()
        
        tickets: List[LinearTicket] = []
        seen: set = set()

        for team_key in self._teams:
            team_id = self._team_ids.get(team_key)
            if not team_id:
                logger.warning("Team '%s' not found in Linear", team_key)
                continue
            
            for t in self._query_team(team_id, team_key):
                if t.key not in seen:
                    seen.add(t.key)
                    tickets.append(t)
                for sub in t.subtasks:
                    if sub.key not in seen:
                        seen.add(sub.key)
                        tickets.append(sub)

        status_names = [ts.name for ts in self._target_statuses]
        logger.info(
            "[%s] Found %d ticket(s) in statuses %s across teams %s",
            self._release_name, len(tickets), status_names, self._teams,
        )
        return tickets

    # Alias for backwards compatibility with release_manager
    def get_qa_ready_tickets(self) -> List[LinearTicket]:
        """Alias for get_ready_tickets() for backwards compatibility."""
        return self.get_ready_tickets()

    def get_ticket(self, ticket_key: str) -> Optional[LinearTicket]:
        """Fetch a single ticket by key (e.g., RUH-123)."""
        query = """
        query Issue($key: String!) {
            issueVcsBranchSearch(branchName: $key) {
                id
                identifier
                title
                state { name }
                assignee { name }
                parent { identifier }
            }
        }
        """
        # Linear's issueVcsBranchSearch might not work well, use issues filter instead
        query = """
        query IssueByKey($filter: IssueFilter!) {
            issues(filter: $filter, first: 1) {
                nodes {
                    id
                    identifier
                    title
                    state { name }
                    assignee { name }
                    parent { identifier }
                }
            }
        }
        """
        # Extract team key and number from ticket key (e.g., "RUH-123" -> team "RUH", number 123)
        parts = ticket_key.split("-")
        if len(parts) != 2:
            logger.error("Invalid ticket key format: %s", ticket_key)
            return None
        
        team_key, number = parts[0], parts[1]
        
        try:
            self._ensure_team_cache()
            team_id = self._team_ids.get(team_key)
            if not team_id:
                logger.error("Team '%s' not found", team_key)
                return None
            
            data = self._graphql(query, {
                "filter": {
                    "team": {"id": {"eq": team_id}},
                    "number": {"eq": int(number)}
                }
            })
            
            nodes = data.get("issues", {}).get("nodes", [])
            if not nodes:
                logger.warning("Ticket %s not found", ticket_key)
                return None
            
            return self._parse_issue(nodes[0])
        except Exception as exc:
            logger.error("Failed to fetch ticket %s: %s", ticket_key, exc)
            return None

    def get_subtasks(self, ticket_key: str) -> List[LinearTicket]:
        """Fetch all subtasks (children) for a ticket."""
        ticket = self.get_ticket(ticket_key)
        if not ticket:
            return []
        
        # Get the internal ID first
        parts = ticket_key.split("-")
        if len(parts) != 2:
            return []
        
        team_key, number = parts[0], parts[1]
        self._ensure_team_cache()
        team_id = self._team_ids.get(team_key)
        if not team_id:
            return []
        
        query = """
        query Children($filter: IssueFilter!) {
            issues(filter: $filter) {
                nodes {
                    id
                    identifier
                    title
                    state { name }
                    assignee { name }
                    parent { identifier }
                }
            }
        }
        """
        try:
            data = self._graphql(query, {
                "filter": {
                    "parent": {"identifier": {"eq": ticket_key}}
                }
            })
            nodes = data.get("issues", {}).get("nodes", [])
            return [self._parse_issue(n, parent_key=ticket_key) for n in nodes]
        except Exception as exc:
            logger.warning("Could not fetch subtasks for %s: %s", ticket_key, exc)
            return []

    def _is_in_target_status(self, status: str) -> bool:
        """Check if a status matches the merged transition target."""
        if not self._merged_transition:
            return False
        target = self._merged_transition.name.upper()
        return status.upper() == target

    def transition_merged_ticket(self, ticket_key: str, transitioned_set: Optional[set] = None) -> bool:
        """
        Transition a ticket to the merged status (e.g., In QA, Released to Prod).
        
        For parent tickets with subtasks, only transitions if ALL subtasks
        are already in the target status. Processes recursively.
        
        Returns True if transition succeeded, False otherwise.
        """
        if transitioned_set is None:
            transitioned_set = set()
        
        # Avoid re-processing
        if ticket_key in transitioned_set:
            return True
        
        if not self._merged_transition:
            logger.debug("No merged_transition configured for release target '%s'", self._release_target)
            return False
        
        # Extract team key from ticket (e.g., "RUH" from "RUH-123")
        team_key = ticket_key.split("-")[0] if "-" in ticket_key else None
        if not team_key:
            logger.warning("Cannot determine team from ticket key: %s", ticket_key)
            return False
        
        # Get the ticket to check current status and subtasks
        ticket = self.get_ticket(ticket_key)
        if not ticket:
            logger.warning("Could not fetch ticket %s", ticket_key)
            return False
        
        # Already in target status?
        if self._is_in_target_status(ticket.status):
            logger.debug("%s already in '%s'", ticket_key, ticket.status)
            transitioned_set.add(ticket_key)
            return True
        
        # Check subtasks first
        subtasks = self.get_subtasks(ticket_key)
        if subtasks:
            # First, try to transition all subtasks recursively
            for sub in subtasks:
                if not self._is_in_target_status(sub.status):
                    self.transition_merged_ticket(sub.key, transitioned_set)
            
            # Re-fetch subtasks to get updated statuses
            subtasks = self.get_subtasks(ticket_key)
            pending_subtasks = [s for s in subtasks if not self._is_in_target_status(s.status)]
            
            if pending_subtasks:
                pending_keys = ", ".join(s.key for s in pending_subtasks)
                logger.info("Skipping %s — subtasks not in target status: %s", ticket_key, pending_keys)
                return False
        
        # Get status name for this team (may vary by team)
        status_name = self._merged_transition.ids.get(team_key, self._merged_transition.name)
        
        # Get the ticket's internal ID and find the target state ID
        try:
            self._ensure_team_cache()
            team_id = self._team_ids.get(team_key)
            if not team_id:
                logger.error("Team '%s' not found", team_key)
                return False
            
            self._ensure_status_cache(team_id)
            state_id = self._status_ids.get(team_id, {}).get(status_name.upper())
            if not state_id:
                logger.error("Status '%s' not found for team '%s'", status_name, team_key)
                return False
            
            # Get the issue ID
            parts = ticket_key.split("-")
            query = """
            query GetIssueId($filter: IssueFilter!) {
                issues(filter: $filter, first: 1) {
                    nodes { id }
                }
            }
            """
            data = self._graphql(query, {
                "filter": {
                    "team": {"id": {"eq": team_id}},
                    "number": {"eq": int(parts[1])}
                }
            })
            nodes = data.get("issues", {}).get("nodes", [])
            if not nodes:
                logger.error("Could not find issue ID for %s", ticket_key)
                return False
            
            issue_id = nodes[0]["id"]
            
            # Update the issue state
            mutation = """
            mutation UpdateIssue($id: String!, $stateId: String!) {
                issueUpdate(id: $id, input: { stateId: $stateId }) {
                    success
                    issue { identifier state { name } }
                }
            }
            """
            result = self._graphql(mutation, {"id": issue_id, "stateId": state_id})
            
            if result.get("issueUpdate", {}).get("success"):
                logger.info("Transitioned %s to '%s'", ticket_key, status_name)
                transitioned_set.add(ticket_key)
                return True
            else:
                logger.error("Failed to transition %s", ticket_key)
                return False
                
        except Exception as exc:
            logger.error("Failed to transition %s: %s", ticket_key, exc)
            return False

    def get_merged_transition_name(self) -> Optional[str]:
        """Get the name of the merged transition status."""
        return self._merged_transition.name if self._merged_transition else None

    # ------------------------------------------------------------------ #

    def _query_team(self, team_id: str, team_key: str) -> List[LinearTicket]:
        """Query all issues in target statuses for a team."""
        self._ensure_status_cache(team_id)
        
        target_names = self._get_target_status_names()
        
        # Find status IDs that match our target statuses
        matching_state_ids = []
        for status_name, status_id in self._status_ids.get(team_id, {}).items():
            if status_name in target_names:
                matching_state_ids.append(status_id)
        
        if not matching_state_ids:
            logger.warning("No matching statuses found for team %s", team_key)
            return []
        
        query = """
        query TeamIssues($filter: IssueFilter!) {
            issues(filter: $filter, first: 200) {
                nodes {
                    id
                    identifier
                    title
                    state { name }
                    assignee { name }
                    parent { identifier }
                    children {
                        nodes {
                            id
                            identifier
                            title
                            state { name }
                            assignee { name }
                            parent { identifier }
                        }
                    }
                }
            }
        }
        """
        
        try:
            data = self._graphql(query, {
                "filter": {
                    "team": {"id": {"eq": team_id}},
                    "state": {"id": {"in": matching_state_ids}}
                }
            })
            
            tickets = []
            for issue in data.get("issues", {}).get("nodes", []):
                ticket = self._parse_issue(issue)
                # Parse subtasks that are also in target status
                children = issue.get("children", {}).get("nodes", [])
                for child in children:
                    child_status = (child.get("state") or {}).get("name", "").upper()
                    if child_status in target_names:
                        ticket.subtasks.append(self._parse_issue(child, parent_key=ticket.key))
                tickets.append(ticket)
            
            return tickets
        except Exception as exc:
            logger.error("Query failed for team %s: %s", team_key, exc)
            return []

    @staticmethod
    def _parse_issue(raw: dict, parent_key: Optional[str] = None) -> LinearTicket:
        return LinearTicket(
            id=raw.get("id", ""),
            key=raw.get("identifier", ""),
            summary=raw.get("title", ""),
            status=(raw.get("state") or {}).get("name", ""),
            issue_type="Issue",  # Linear doesn't have issue types like Jira
            assignee=(raw.get("assignee") or {}).get("name"),
            parent_key=parent_key or (raw.get("parent") or {}).get("identifier"),
        )
