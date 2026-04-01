---
name: trd-generation
description: >
  Technical Requirement Document generation methodology for feature issues. Use this skill
  when an issue has been classified as a feature. Covers: requirements extraction, technical
  design, service mapping, data model and API changes, acceptance criteria definition.
  Always load this skill before generating any TRD.
---

# TRD Generation Skill

## Methodology: Requirements → Design → Impact → Acceptance

### Step 1 — Extract Requirements

From the issue, separate:

**Functional Requirements (what it does):**
- User-facing behavior
- System-facing behavior
- Input/output contracts
- Business rules

**Non-Functional Requirements (how well it does it):**
- Performance expectations
- Security constraints
- Scalability needs
- Backward compatibility

**Implicit Requirements (not stated but needed):**
- Error handling for new flows
- Validation on new inputs
- Auth/permission checks on new endpoints
- Logging and observability for new paths
- Database indexes for new query patterns

### Step 2 — Design the Approach

Read existing code patterns FIRST. The design must follow existing conventions:

**For each affected repo:**
1. Read the router/handler pattern — follow it
2. Read the service layer pattern — follow it
3. Read the model/schema pattern — follow it
4. Read the test pattern — follow it

**Design decisions to make:**
- Where does the new logic live? (new file vs existing file)
- New models or extensions to existing models?
- New endpoints or modifications to existing ones?
- New gRPC methods or extensions to existing protos?
- New Kafka topics or new consumers on existing topics?
- New config/env variables needed?

### Step 3 — Map Service Impact

Use the knowledge graph to trace the feature through services:

```
Example: "Add message reactions"

1. agent-gateway: New REST endpoint POST /conversations/{id}/messages/{id}/reactions
2. communication-service: New gRPC method AddReaction, new field in MessageModel
3. agent-platform-v2: No change (reactions don't affect agent logic)
4. ai-proxy: No change
5. proto-definitions: New proto message and RPC method
```

For each impacted service, go into the repo and verify:
- The file exists where you expect it
- The pattern you plan to follow is current
- No recent refactors invalidate your design

### Step 4 — Define Data Model Changes

If the feature needs data changes:

```markdown
### New Fields
| Model | Field | Type | Default | Index | Migration |
|-------|-------|------|---------|-------|-----------|
| MessageModel | reactions | List[Reaction] | [] | No | Additive — no migration needed |

### New Models
| Model | Collection | Purpose |
|-------|-----------|---------|
| Reaction | embedded in Message | Stores user reactions |

### Schema Changes (gRPC)
| Proto File | Change |
|-----------|--------|
| communication.proto | Add `repeated Reaction reactions` to Message |
```

### Step 5 — Define API Changes

```markdown
### New Endpoints
| Method | Path | Auth | Request | Response |
|--------|------|------|---------|----------|
| POST | /conversations/{id}/messages/{id}/reactions | JWT | AddReactionRequest | ReactionResponse |

### Modified Endpoints
| Method | Path | Change |
|--------|------|--------|
| GET | /conversations/{id}/messages | Include reactions in response |

### New gRPC Methods
| Service | Method | Request | Response |
|---------|--------|---------|----------|
| CommunicationService | AddReaction | AddReactionRequest | AddReactionResponse |
```

### Step 6 — Define Acceptance Criteria

Every TRD must have testable acceptance criteria:

```markdown
- [ ] User can add a reaction to a message
- [ ] User can remove their own reaction
- [ ] Reactions are persisted and returned in message queries
- [ ] Only authenticated users can react
- [ ] Duplicate reactions from same user are rejected
```

## Verification Gates

Before finalizing the TRD:
- [ ] All functional requirements addressed
- [ ] Design follows existing repo patterns
- [ ] Data model changes defined (or explicitly "none")
- [ ] API changes defined (or explicitly "none")
- [ ] Cross-repo impacts mapped
- [ ] Acceptance criteria are testable
- [ ] Complexity estimate provided with justification
