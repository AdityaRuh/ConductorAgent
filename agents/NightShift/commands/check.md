---
name: check
description: Check the processing status of a specific ticket
---

# /check

Check logs for a specific ticket.

## Usage
```
/check RUH-384
```

## Execution

```bash
# Search logs for the ticket
docker logs nightshift 2>&1 | grep "RUH-384"

# Check Claude output for the ticket
docker exec nightshift cat /app/logs/claude_RUH-384.log 2>/dev/null | tail -50

# Check if PR was created
docker exec nightshift cat /app/logs/pr_body_RUH-384.txt 2>/dev/null

# Check prompt sent to Test Agent
docker exec nightshift wc -c /app/logs/prompt_test_RUH-384.txt 2>/dev/null

# Check prompt sent to Dev Agent
docker exec nightshift wc -c /app/logs/prompt_impl_RUH-384.txt 2>/dev/null
```
