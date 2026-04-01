---
name: pathfinder-reader
description: Parse Pathfinder analysis comments (RCA for bugs, TRD for features) to extract repos, file hints, and code changes
---

# Pathfinder Reader

Parses structured comments left by the Pathfinder automation on Linear tickets.

## How to Execute

### Step 1: Fetch Comments

```bash
curl -s -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"query(\$id: String!) { issue(id: \$id) { comments(first: 50) { nodes { body createdAt user { name } } } } }\", \"variables\": {\"id\": \"$ISSUE_ID\"}}" \
  | jq '.data.issue.comments.nodes'
```

### Step 2: Find Pathfinder Comment

Look for a comment body containing the text `Pathfinder Analysis`. This is the Pathfinder comment.

### Step 3: Extract Structured Data

From the Pathfinder comment body, extract:

| Field | Pattern | Example |
|---|---|---|
| Classification | `**Classification:** WORD` | `**Classification:** BUG` |
| Complexity | `**Complexity:** WORD` | `**Complexity:** XL` |
| Repos | `**Repos Affected:** repo1 (primary), repo2` | `agent-platform-v2, ai-gateway` |
| Repos (alt) | `#### Repo N: \`repo-name\` (Note)` | `#### Repo 1: \`agent-platform-v2\` (Primary Changes)` |
| Code Changes | Markdown table: `\| file/path.py \| function() \| MODIFY \| description \|` | See below |
| File Hints | Backtick code refs: `` `path/file.py` `` or `` `path/file.py:function()` `` | |
| Impl Order | `## Implementation Order` section with numbered `**repo-name**` entries | |

### Code Changes Table Format

```
| File | Function | Type | Description |
|---|---|---|---|
| src/services/redis.py | connect() | MODIFY | Add TLS support |
| src/config/base.py | Settings | MODIFY | Add REDIS_USE_TLS field |
```

Parse each row where the first column contains a `/` (file path indicator). Extract:
- `repo` — from the nearest repo header above the table
- `file` — column 1
- `function` — column 2
- `change_type` — column 3 (MODIFY, ADD, NEW FILE, VERIFY)
- `description` — column 4

### Step 4: Output

Report the extracted data:
```
Classification: BUG
Complexity: XL
Repos: agent-platform-v2 (primary), agent-gateway
Code Changes:
  [agent-platform-v2] MODIFY src/services/redis.py → connect() — Add TLS support
  [agent-gateway] MODIFY src/config/base.py → Settings — Add REDIS_USE_TLS field
File Hints: src/services/redis.py, src/config/base.py
```

If no Pathfinder comment found, report: `"No Pathfinder analysis found — using ticket description as context."`
