"""Linear GraphQL client for ticket lookup and status transitions."""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"

# Regex to extract Linear ticket IDs from branch names.
# Matches patterns like: TT-123, SDR-45, RP-678, RUH-12, M3-9
# In branches like: TT-123/feature, feature/TT-123-something, TT-123-fix-bug
TICKET_ID_PATTERN = re.compile(r"\b([A-Z]{1,5}-\d+)\b")


def extract_ticket_id(branch_name: str) -> Optional[str]:
    """Extract a Linear ticket ID from a git branch name.

    Supports common patterns:
      - TT-123/feature-name
      - feature/TT-123-something
      - TT-123-fix-bug
      - TT-123
    """
    match = TICKET_ID_PATTERN.search(branch_name.upper())
    if match:
        return match.group(1)
    return None


class LinearClient:
    """Async client for the Linear GraphQL API."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
        )

    async def _query(self, query: str, variables: dict | None = None) -> dict:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = await self._http.post(LINEAR_API_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            logger.error("Linear GraphQL errors: %s", data["errors"])
            raise Exception(f"Linear API error: {data['errors']}")
        return data.get("data", {})

    async def find_issue(self, ticket_id: str) -> Optional[dict]:
        """Look up a Linear issue by its identifier (e.g., TT-123).

        Returns dict with: id, identifier, title, state {id, name, type}, team {id, key}
        """
        query = """
        query($filter: IssueFilter) {
            issues(filter: $filter, first: 1) {
                nodes {
                    id
                    identifier
                    title
                    url
                    state { id name type }
                    team { id key name }
                }
            }
        }
        """
        # Split identifier into team key and number
        parts = ticket_id.split("-")
        if len(parts) != 2:
            return None

        team_key, number_str = parts
        try:
            number = int(number_str)
        except ValueError:
            return None

        variables = {
            "filter": {
                "team": {"key": {"eq": team_key}},
                "number": {"eq": number},
            }
        }

        data = await self._query(query, variables)
        nodes = data.get("issues", {}).get("nodes", [])
        return nodes[0] if nodes else None

    async def get_team_states(self, team_id: str) -> list[dict]:
        """Get all workflow states for a team."""
        query = """
        query($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes { id name type }
                }
            }
        }
        """
        data = await self._query(query, {"teamId": team_id})
        return data.get("team", {}).get("states", {}).get("nodes", [])

    async def transition_issue(self, issue_id: str, target_state_id: str) -> bool:
        """Move an issue to a new state. Returns True on success."""
        mutation = """
        mutation($issueId: String!, $stateId: String!) {
            issueUpdate(id: $issueId, input: { stateId: $stateId }) {
                success
                issue { id identifier state { name } }
            }
        }
        """
        data = await self._query(mutation, {"issueId": issue_id, "stateId": target_state_id})
        result = data.get("issueUpdate", {})
        success = result.get("success", False)
        if success:
            issue = result.get("issue", {})
            logger.info(
                "Linear: transitioned %s to '%s'",
                issue.get("identifier", "?"),
                issue.get("state", {}).get("name", "?"),
            )
        return success

    async def transition_to_state_by_name(
        self, ticket_id: str, target_state_name: str
    ) -> Optional[str]:
        """Find an issue and transition it to a named state.

        Args:
            ticket_id: e.g., "TT-123"
            target_state_name: e.g., "Code Review" (case-insensitive)

        Returns:
            The new state name on success, None on failure.
        """
        issue = await self.find_issue(ticket_id)
        if not issue:
            logger.warning("Linear: issue %s not found", ticket_id)
            return None

        current_state = issue["state"]["name"]
        target_lower = target_state_name.lower()

        # Don't transition if already in the target state
        if current_state.lower() == target_lower:
            logger.info("Linear: %s already in '%s', skipping", ticket_id, current_state)
            return current_state

        # Find the target state in the team's workflow
        team_id = issue["team"]["id"]
        states = await self.get_team_states(team_id)

        target_state = None
        for s in states:
            if s["name"].lower() == target_lower:
                target_state = s
                break

        if not target_state:
            # Try partial match (e.g., "ready to deploy" matches "Ready to Deploy- QA")
            for s in states:
                if target_lower in s["name"].lower():
                    target_state = s
                    break

        if not target_state:
            logger.warning(
                "Linear: state '%s' not found for team %s (available: %s)",
                target_state_name,
                issue["team"]["key"],
                [s["name"] for s in states],
            )
            return None

        success = await self.transition_issue(issue["id"], target_state["id"])
        return target_state["name"] if success else None

    async def add_comment(self, issue_id: str, body: str) -> bool:
        """Add a comment to a Linear issue."""
        mutation = """
        mutation($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                success
            }
        }
        """
        data = await self._query(mutation, {"issueId": issue_id, "body": body})
        return data.get("commentCreate", {}).get("success", False)

    async def close(self):
        await self._http.aclose()
