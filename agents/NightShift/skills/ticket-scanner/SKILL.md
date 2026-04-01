---
name: ticket-scanner
description: Fetch eligible tickets from Linear API, filter by state and assignee, sort by priority
---

# Ticket Scanner

Connects to Linear GraphQL API and fetches tickets that are ready for autonomous development.

## How to Execute

### Step 1: Authenticate
```bash
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ viewer { id name email } }"}' | jq '.data.viewer'
```
Save the `id` as `VIEWER_ID`.

### Step 2: Get Teams
```bash
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ teams { nodes { id name key } } }"}' | jq '.data.teams.nodes'
```

### Step 3: Fetch Eligible Tickets (per team)

```bash
QUERY='query($teamId: ID!, $assigneeId: ID!) {
  issues(
    filter: {
      team: { id: { eq: $teamId } }
      state: { name: { eqIgnoreCase: "READY FOR DEVELOPMENT" } }
      assignee: { id: { eq: $assigneeId } }
    }
    first: 20
  ) {
    nodes {
      id identifier title description url priority
      labels { nodes { name } }
      project { name }
      team { id key }
      state { name type }
    }
  }
}'

curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$(echo $QUERY | tr '\n' ' ')\", \"variables\": {\"teamId\": \"$TEAM_ID\", \"assigneeId\": \"$VIEWER_ID\"}}" \
  | jq '.data.issues.nodes'
```

If no results, retry with fallback filter (type-based instead of name-based):
```graphql
state: { type: { in: ["unstarted", "started"] } }
```

### Step 4: Filter and Sort

- **Exclude** tickets with labels `claude-processing` or `claude-done`
- **Sort** by priority: Urgent (1) > High (2) > Medium (3) > Low (4) > None (0 = last)

### Step 5: Output

For each eligible ticket, display:
```
TICKET-ID  [Priority]  Title
  State: <state> | Labels: <labels>
```
