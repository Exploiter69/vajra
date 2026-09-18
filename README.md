# VAJRA

VAJRA is a local-first, model-agnostic autonomous engineering runtime built around durable Engineering Runs, trusted execution, isolated workspaces, deterministic policy, independent verification, recovery, human control, and provenance-bound engineering memory.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram bot, model-hosting platform, or collection of shell scripts.

## Current Status

**Phase 14 — Engineering Memory: COMPLETE / CLOSED.**

Phases 6–9 established the durable execution substrate, autonomous control/truth boundaries, engineering context/workspaces, and independent verification/anti-gaming. Phase 10 established the bounded autonomous objective-to-evidence loop. Phase 11 validated durability and chaos behavior. Phase 12 added capability-aware model/worker routing. Phase 13 added the always-on control plane. Phase 14 adds provenance-bound memory without making history authoritative.

**Operating-cost constraint:** ₹0.00. No paid inference or infrastructure is a project dependency.

## Phase 14 implementation

- src/vajra/memory/contracts.py — immutable memory records, query and conflict contracts
- src/vajra/memory/store.py — append-only fsync-backed JSONL persistence with tamper detection and supersession
- src/vajra/memory/service.py — failure/repository/context memory facade and current-state validation
- tests/memory/test_phase14_memory.py — Phase 14 gate coverage
- docs/PHASE_14_IMPLEMENTATION.md — roadmap-to-implementation mapping
- .github/workflows/phase14-validation.yml — free hosted validation

### 14A — Failure Memory

Failure signatures and outcomes are stored with Run/Step/Attempt identity, repository state, and mandatory source references. Memory informs recovery reasoning but cannot authorize recovery or completion.

### 14B — Repository Memory

Architecture, conventions, structured decisions, and verification history are retained with repository revision/digest. Historical repository memory is stale when current repository truth changes.

### 14C — Context Memory

Useful bounded context is retained with repository revision, context digest, item provenance, and source references. Context memory is invalidated by current-state changes rather than silently reused.

### 14D — Conflict Awareness

Current repository and verification truth outrank historical memory. Corrections are append-only records linked with supersedes; normal queries hide superseded history while preserving it for audit.

**Phase 14 gate:** CLOSED after dedicated memory tests, portable full suite, compilation, diff checks, and GitHub Actions validation pass.

Phase 14 deliberately does not introduce a vector database, embeddings, autonomous memory rewriting, model-controlled memory authority, or paid infrastructure.

## Phase 13 implementation

Phase 13 provides the always-on daemon, durable queue, human controls, scheduling, and localhost-by-default HTTP/JSON control surface. Canonical Run state remains in the Run plane.

## Phase 12 implementation

Phase 12 provides model identity/versioning, capability-based worker routing, deterministic selection, budget-aware routing, routing evidence, and bounded model/worker switching without bypassing Policy, Broker, leases, or independent Verification.

## Phase 11 implementation

Phase 11 validates unattended durability under failure with kill/recovery harnesses, state divergence, retry storms, lease fencing, and real elapsed-time soak profiles.

## Architectural Laws

1. Model Is Not Authority
2. VAJRA Owns Canonical State
3. Meaningful Operations Are Durable
4. Reasoning Cannot Directly Execute
5. Worktree Isolation Is Not Security Isolation
6. Verification Is External
7. Failure Is Data
8. Autonomy Is Bounded
9. Progress Requires Evidence
10. Human Is Ultimate Authority
11. Fresh Reality Before Autonomous Decision
12. Evidence-Bound Progress
13. No Ambiguous Continuation
14. Operation Identity
15. Controller Cannot Bypass Authority
16. Historical Information Is Not Current Truth

## Repository Documentation

- docs/VAJRA_v0_Technical_Specification.txt — canonical v0 architecture/specification
- docs/VAJRA_v1_Architecture_and_Roadmap_Specification.md — converged roadmap
- docs/CURRENT_STATE.md — current implementation/gate state
- docs/PHASE_7_DESIGN_FREEZE.md — Phase 7 safety/control design freeze
- docs/PHASE_8_IMPLEMENTATION.md — context/workspace implementation
- docs/PHASE_9_IMPLEMENTATION.md — verification/anti-gaming implementation
- docs/PHASE_9_GATE_RESULT.md — Phase 9 closure record
- docs/PHASE_10_IMPLEMENTATION.md — Phase 10 implementation and closure evidence
- docs/PHASE_11_IMPLEMENTATION.md — Phase 11 implementation and closure evidence
- docs/PHASE_11_GATE_RESULT.md — Phase 11 gate closure record
- docs/PHASE_12_IMPLEMENTATION.md — Phase 12 implementation and closure evidence
- docs/PHASE_13_IMPLEMENTATION.md — Phase 13 implementation and roadmap mapping
- docs/PHASE_13_GATE_RESULT.md — Phase 13 gate closure record
- docs/PHASE_14_IMPLEMENTATION.md — Phase 14 implementation and roadmap mapping

## Frozen Baseline

v0.1.0 / fb3cca5 remains the immutable Phase 6 baseline. Later work proceeds on main without rewriting or retagging that baseline.
