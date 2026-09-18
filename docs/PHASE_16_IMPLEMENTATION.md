# VAJRA Phase 16 — Advanced Autonomy

**Status:** IMPLEMENTED / GATE PENDING

Phase 16 follows the canonical roadmap in `vajra3`: 16A multi-step engineering, 16B explicit multi-repository authority, 16C specialized workers without a default swarm, and 16D bounded complex/long-horizon objectives.

## 16A — Multi-step engineering

`src/vajra/autonomy/advanced.py` introduces `MultiStepObjective` and `AdvancedStage`. A stage graph is validated as a DAG with unique IDs and explicit dependencies. The engine advances only when dependencies are complete.

The canonical example is represented as explicit stages:

`inspect → design → config/implementation → tests → integration → security → documentation → final verification`.

Each executable stage can be routed to one specialized role and must cross the supplied execution and independent-verification callbacks. The advanced layer coordinates; it does not become a new execution authority.

## 16B — Multi-repository

`RepositoryAuthority` declares repository identity, workspace identity, base revision, and allowed operations. `CrossRepositoryOperation` carries a unique operation identity, intent identity, explicit repository set, and reason.

`AdvancedAutonomyEngine.authorize_operation()` rejects repository identities outside the objective's explicit authority set and rejects duplicate repository identities. Cross-repository work therefore cannot silently expand its repository scope.

## 16C — Specialized workers

`WorkerSpecialization` defines coding, testing, security, research, and documentation roles. `SpecializedWorkerRegistry` performs deterministic singular selection for a requested role/capability set.

This is deliberately not a swarm. Workers remain subordinate resources; Policy, Execution Broker, leases/fencing, sandbox/workspace controls, and independent Verification remain the authority chain.

## 16D — Complex / long-horizon objectives

`LongHorizonLimits` provides hard bounds for stages, replans, model-call budget declaration, attempts, and wall-clock runtime. `AdvancedRunStore` is an append-only fsync-backed JSONL stage checkpoint journal.

A resumed engine reconstructs completed stages from durable checkpoints and skips them. Failed verification never creates a completion checkpoint. Bound exhaustion fails closed.

The long-horizon layer is therefore resumable rather than dependent on one process, model session, or worker lifetime.

## Authority and safety

Phase 16 does not alter canonical Run state ownership or create a parallel policy/execution/verifier authority. The engine's callbacks are explicitly expected to use the existing Phase 7–15 boundaries.

No model output is trusted as completion proof. Verification evidence is required before a stage is marked complete.

No multi-agent swarm, automatic self-modification, paid service, or new external dependency is introduced.

## Validation

The Phase 16 gate must pass:

1. dedicated `tests/autonomy/test_phase16_advanced.py`;
2. portable full suite with `gvisor_integration` excluded;
3. `python -m compileall -q src tests`;
4. `git diff --check`.

Phase 16 is not closed until all four checks pass.
