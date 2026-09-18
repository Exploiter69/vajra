# Phase 17 — Controlled Self-Improvement

## Scope

Phase 17 implements the roadmap's complete Controlled Self-Improvement boundary.

VAJRA may improve bounded heuristics for routing, recovery, context ranking, failure classification, memory strategies, scheduling, and worker selection.

Self-improvement is a proposal-and-promotion workflow, not autonomous mutation.

## Protected forever

Policy authority, security boundary, sandbox primitives, verification authority, worker fencing, canonical state, human override, audit/event integrity, Execution Broker boundary, autonomy/control-plane authority, and the self-improvement guard itself are outside the self-improvement scope.

A proposal touching a protected path is rejected before isolation or execution.

## Lifecycle

```text
model / operator proposal
        ↓
scope validation
        ↓
isolated branch
        ↓
tests
        ↓
independent verification
        ↓
security verification
        ↓
human approval
        ↓
promotion
```

There is deliberately no model → modify VAJRA → restart-itself path.

## Durable state

`SelfImprovementStore` records the proposal lifecycle in an append-only, fsync-backed JSONL journal. Restart reloads the last durable state and validates journal sequence continuity.

## Promotion boundary

Promotion requires the proposal to be `AWAITING_HUMAN`, an explicit matching `PromotionDecision`, non-empty approver identity, an explicit approval token, and a supplied promotion callback. The engine never manufactures approval and never invokes promotion before the human gate.

## Safety properties

- only roadmap-listed improvement areas are eligible;
- unsafe and traversal paths are rejected;
- protected authority surfaces cannot be changed through this subsystem;
- tests, independent verification, and security verification are mandatory;
- human approval is mandatory;
- promotion is explicit and durable;
- failed/rejected proposals cannot silently become promoted;
- no paid dependency or external service is required.

## Validation

`tests/self_improvement/test_phase17_self_improvement.py` covers durability, protected surfaces, unsafe paths, the complete lifecycle, test/verification/security failures, human-gate enforcement, duplicate promotion, rejection, and journal tampering.
