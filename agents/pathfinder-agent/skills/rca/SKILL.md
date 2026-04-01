---
name: rca
description: >
  Root cause analysis methodology for bug issues. Use this skill when an issue has been
  classified as a bug. Covers: symptom identification, cause tracing through code,
  root cause isolation, fix approach proposal, and affected file mapping.
  Always load this skill before performing any RCA.
---

# Root Cause Analysis Skill

## Methodology: 5 Whys + Code Trace

### Step 1 — Define the Symptom
Write a single, precise sentence:
- **Bad:** "The API is broken"
- **Good:** "POST /agents/chat/stream returns 500 when the conversation has more than 50 messages"

Extract from the issue:
- What endpoint/feature is affected?
- What is the error code/message?
- Is it consistent or intermittent?
- When did it start?

### Step 2 — Hypothesize Probable Causes

Before touching code, list 2-4 hypotheses based on your knowledge of the system:

```
Hypothesis 1: Message pagination in communication-service hits memory limit at >50 messages
Hypothesis 2: Token count exceeds model context window, ai-proxy returns malformed response
Hypothesis 3: Redis stream buffer overflows for large conversation histories
```

Use the knowledge graph to inform hypotheses — it tells you which services are in the request path.

### Step 3 — Trace Through Code

For each hypothesis:
1. Identify the entry point (API endpoint, gRPC method, Kafka consumer)
2. Read the handler code
3. Follow the call chain: router → service → repository/client → external
4. Look for:
   - Missing error handling
   - Wrong assumptions about data size/shape
   - Race conditions in async code
   - Missing null/empty checks
   - Hardcoded limits
   - Recent changes in the area (git log)

### Step 4 — Isolate Root Cause

The root cause is the **deepest** reason the bug exists, not the proximate cause:

```
Proximate cause: API returns 500
       ↓
Why: Service throws unhandled exception
       ↓
Why: MongoDB query times out
       ↓
Why: No index on conversation_id + created_at
       ↓
ROOT CAUSE: Missing compound index causes full collection scan on large conversations
```

### Step 5 — Propose Fix

Define:
- What code changes fix the root cause (not just the symptom)
- Which files and functions need modification
- Whether the fix requires data migration
- What tests verify the fix
- What regression risks exist

## Common Root Cause Categories

| Category | Example | Typical Location |
|----------|---------|-----------------|
| **Missing validation** | No input size check | Router/schema layer |
| **Missing error handling** | Unhandled exception in async | Service layer |
| **Data model issue** | Missing index, wrong field type | Model/DB layer |
| **Race condition** | Concurrent writes to same resource | Service layer |
| **Configuration** | Wrong env var, missing config | Config/deployment |
| **Integration** | Service A sends format B doesn't expect | gRPC/Kafka boundary |
| **Regression** | Recent PR broke existing behavior | Varies — check git log |

## Verification Gates

Before finalizing the RCA:
- [ ] Symptom is precisely defined (not vague)
- [ ] Root cause is traced to specific code, not guessed
- [ ] Fix approach addresses root cause, not just symptom
- [ ] Cross-repo impacts identified
- [ ] Testing requirements listed
