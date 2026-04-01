---
name: status
description: Show NightShift container status and recent logs
---

# /status

Show container health and recent activity.

## Usage
```
/status
```

## Execution

```bash
# Container status
docker ps --filter name=nightshift --format "table {{.Status}}\t{{.RunningFor}}"

# Recent logs
docker logs nightshift --tail 30
```
