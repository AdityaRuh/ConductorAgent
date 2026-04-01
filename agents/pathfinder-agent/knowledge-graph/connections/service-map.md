# Service Map — Ruh AI Backend

> How all backend services connect, communicate, and depend on each other.

**Last updated:** 2026-03-25

## Service Overview

```
                    ┌─────────────────┐
                    │   External       │
                    │   Clients        │
                    │  (REST/SSE)      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  agent-gateway   │  Port: 8001
                    │  (FastAPI)       │  Auth: JWT/API-Key/SDR
                    └──┬──────┬───┬───┘
                       │      │   │
            ┌──────────┘      │   └──────────────┐
            │ gRPC            │ Kafka             │ HTTP
            ▼                 ▼                   ▼
  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐
  │ communication-   │  │ agent-       │  │ ai-proxy     │  Port: 5511
  │ service          │  │ platform-v2  │  │ (FastAPI)    │
  │ (gRPC)           │  │              │  └──────┬───────┘
  │ Port: 50055      │  │              │         │ HTTPS
  └──────────────────┘  └──────────────┘         ▼
          │                    │           ┌──────────────┐
          ▼                    │           │  OpenRouter   │
     MongoDB                   │           │  API          │
                               │           └──────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │  Also connects   │
                    │  to:             │
                    │  - user-service  │
                    │  - agent-service │
                    │  (gRPC)          │
                    └──────────────────┘
```

## Connection Details

### agent-gateway → communication-service
- **Protocol:** gRPC
- **Port:** 50055
- **Purpose:** Read/write conversations and messages
- **Key operations:** Create conversation, list messages, send message, get history
- **Impact:** If communication-service changes a gRPC method signature, agent-gateway must update its client stubs

### agent-gateway → agent-platform-v2
- **Protocol:** Kafka
- **Topics:**
  - `agent_chat_requests` (gateway → platform): New chat requests
  - `agent_chat_responses` (platform → gateway): Agent responses
  - `agent_session_deletion_requests` (gateway → platform): Session cleanup
  - `agent_task_requests` (gateway → platform): Task execution
- **Impact:** Kafka message schema changes affect both services

### agent-gateway → ai-proxy
- **Protocol:** HTTP
- **Port:** 5511
- **Purpose:** LLM inference requests (fallback/direct)
- **Key endpoint:** POST /v1/chat/completions
- **Impact:** Changes to ai-proxy request/response format affect agent-gateway

### agent-platform-v2 → communication-service
- **Protocol:** gRPC
- **Port:** 50055
- **Purpose:** Read conversation history for agent context
- **Impact:** Agent platform needs conversation data to build prompts

### agent-platform-v2 → ai-proxy
- **Protocol:** HTTP
- **Port:** 5511
- **Purpose:** LLM calls during agent execution loop
- **Impact:** Model changes or new parameters in ai-proxy affect agent execution

## Shared Dependencies

### proto-definitions
- **Location:** `/Users/Akshit/Desktop/RUH/BE/proto-definitions`
- **Used by:** All gRPC services (communication-service, agent-gateway, agent-platform-v2)
- **Impact:** Proto changes require stub regeneration in ALL consuming services

### Redis
- **Used by:** agent-gateway (caching, stream buffering)
- **Port:** 6379
- **Impact:** Redis key pattern changes in agent-gateway affect stream consumers

### Kafka
- **Used by:** agent-gateway (producer), agent-platform-v2 (consumer)
- **Broker:** Port 9092
- **Impact:** Topic or message schema changes require both producer and consumer updates

### MongoDB
- **Used by:** communication-service (primary data), ai-proxy (logging)
- **Impact:** Schema changes in communication-service models affect query patterns

## Cross-Cutting Change Scenarios

### Scenario: Add a new field to messages
1. `communication-service` — add field to MessageModel + migration
2. `proto-definitions` — update Message proto
3. `communication-service` — regenerate stubs, update `to_proto()`
4. `agent-gateway` — regenerate stubs, expose in REST response
5. `agent-platform-v2` — regenerate stubs (if it reads messages)

### Scenario: Add a new API endpoint
1. `agent-gateway` — new router + schema + service
2. If it needs data → `communication-service` may need new gRPC method
3. If it needs proto → `proto-definitions` update first

### Scenario: Change LLM request format
1. `ai-proxy` — modify proxy service
2. `agent-platform-v2` — update LLM client calls
3. `agent-gateway` — update if it makes direct LLM calls

### Scenario: Add a new Kafka topic
1. `agent-gateway` — add producer
2. `agent-platform-v2` — add consumer (or vice versa)
3. Kafka cluster — create topic (deployment config)

## Other Services (not in primary portfolio)

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| user-service | 50052 | gRPC | User data management |
| agent-service | 50057 | gRPC | Agent configuration |
| scheduler-service | — | — | Scheduled task execution |
| payment-service | — | — | Billing and payments |
| api-gateway | — | — | API gateway (legacy?) |
