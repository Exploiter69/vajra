# VAJRA Phase 7 — Safety Foundation Design Freeze

**Status:** Design freeze candidate
**Baseline:** `ba7f239`
**Purpose:** Define the minimum contracts that must exist before VAJRA gains autonomous controller authority.

## 1. Why this freeze exists

Phase 6 provides the execution substrate: durable run/step/attempt lifecycle, worker leasing and fencing, policy authority, execution brokerage, verification, failure recovery, CLI control, remote worker transport, and sandbox backends.

Phase 7 must not simply add a loop around those components. The controller must be unable to promote work on model claims, stale state, mutable acceptance criteria, duplicated effects, or an unverified artifact.

Therefore the following contracts are frozen before autonomous controller implementation:

1. Acceptance Criteria
2. Progress and Completion Predicates
3. Operation Identity and Idempotency
4. Reality Reconciliation
5. Worktree Ownership
6. Evidence Integrity and Linkage
7. Transition Authority
8. Controller Authority Boundary

## 2. Architectural laws enforced

Phase 7 implementation MUST preserve:

- Model Is Not Authority.
- VAJRA Owns Canonical State.
- Meaningful Operations Are Durable.
- Reasoning Cannot Directly Execute.
- Worktree Isolation Is Not Security Isolation.
- Verification Is External.
- Failure Is Data.
- Autonomy Is Bounded.
- Progress Requires Evidence.
- Fresh Reality Before Autonomous Decision.
- Evidence-Bound Progress.
- No Ambiguous Continuation.
- Operation Identity.
- Controller Cannot Bypass Authority.
- Historical Information Is Not Current Truth.

## 3. Frozen control flow

```text
Objective
  -> Frozen Acceptance Criteria
  -> Workspace/Reality Observation
  -> Reconciliation Report
  -> Context Bundle
  -> Reasoning/Model
  -> Intent
  -> Policy Decision
  -> Execution Request
  -> Broker
  -> Worktree/Sandbox
  -> Artifact
  -> Independent Verification
  -> Evidence
  -> Progress Record
  -> Controller Decision
  -> next action / recovery / human / completion
```

A controller decision without a fresh reconciliation report is invalid.

A completion decision without frozen acceptance criteria and independent verification evidence is invalid.

A model output that directly mutates canonical state is invalid.

## 4. Acceptance Criteria contract

`AcceptanceCriteria` is immutable for the lifetime of a Run.

Minimum fields:

- `criteria_id`
- `version`
- `run_id`
- `objective_digest`
- `artifact_contract`
- `verification_requirements`
- `completion_predicate`
- `compiled_at`
- `compiler_version`
- `criteria_digest`

Rules:

- Criteria are compiled before autonomous execution begins.
- Criteria cannot be changed by a worker or model.
- Any human change creates a new explicit version and requires a controlled Run transition.
- Criteria must be machine-checkable or explicitly classified as requiring human judgment.
- An uncompilable objective cannot silently become an unconstrained autonomous run.

## 5. Progress contract

Progress is evidence-backed state change, not model confidence.

`ProgressRecord` MUST identify:

- Run/Step/Attempt
- previous progress state
- new progress state
- observed artifact digest/revision
- verification evidence references
- reconciliation report reference
- operation identity
- timestamp
- deterministic progress predicate result

`CompletionPredicate` MUST require, at minimum:

```text
objective satisfied
AND acceptance criteria satisfied
AND required artifact exists
AND artifact is current
AND independent verification passes
AND evidence is internally consistent
AND no unresolved authority/safety anomaly exists
```

No-progress detection remains useful but cannot itself establish completion.

## 6. Operation identity and idempotency

Every meaningful externally visible operation receives a stable `OperationIdentity`.

Minimum fields:

- `operation_id`
- `run_id`
- `step_id`
- `attempt_id`
- `intent_id`
- `operation_type`
- `parameters_digest`
- `fencing_token`
- `idempotency_key`

The broker MUST evaluate operation identity before invoking an effectful backend.

Repeated delivery of the same operation identity MUST NOT create an additional logical side effect where the backend supports idempotency.

An operation whose external side effect cannot be made idempotent MUST be explicitly classified as non-replayable and require a durable recovery policy.

Operation result records MUST carry an effect/result digest where practical.

## 7. Reality reconciliation

Durable state is a claim about reality, not reality itself.

`ReconciliationReport` MUST distinguish at least:

- canonical VAJRA state
- persisted event/checkpoint state
- Git/worktree state
- workspace filesystem state
- sandbox state
- worker lease state
- verification state
- evidence state

Each observation has a source, timestamp, freshness, and digest where applicable.

Authority precedence is frozen conceptually as:

```text
Current external verification / repository reality
        > current workspace observations
        > worker self-report
        > historical event/checkpoint claims
```

The exact precedence for each resource type MUST be represented explicitly in code rather than inferred by the controller.

Conflicting observations are anomalies. The controller MUST NOT silently choose a convenient interpretation.

Recovery MUST reconcile actual external state before issuing a new effectful operation.

## 8. Worktree ownership

Every autonomous Run that can mutate repository state MUST have an explicitly owned workspace/worktree contract before execution.

The contract identifies:

- repository
- base revision
- worktree path
- ownership/run ID
- expected revision
- mutable paths
- Git concurrency policy
- cleanup policy

The worktree is an isolation boundary for repository state, not a security boundary. Security isolation remains the sandbox's responsibility.

A controller MUST NOT authorize repository mutation without a valid workspace contract.

## 9. Evidence integrity

Evidence is distinct from the mutable event stream.

Evidence references MUST be content-addressable or otherwise integrity-protected where feasible.

The evidence chain is:

```text
Intent
 -> Policy Decision
 -> Execution
 -> Artifact
 -> Verification
 -> Evidence
 -> Progress
 -> Controller Decision
```

Every completion-relevant ProgressRecord MUST reference the evidence supporting it.

Conflicting evidence MUST produce an anomaly rather than an implicit last-write-wins result.

Evidence retention and growth limits are mandatory design concerns.

## 10. Transition authority

The existing transition table remains the legality foundation.

Phase 7 adds authority semantics:

- only the authoritative controller/recovery authority may perform autonomous state transitions;
- Policy remains the authorization authority for operations;
- the model cannot transition Runs;
- workers cannot transition Runs;
- verification cannot directly transition Runs;
- CLI human actions remain an explicit higher-priority authority path;
- every transition records its cause and supporting evidence.

The implementation MUST reject illegal or unauthorized transitions rather than relying on callers to behave correctly.

## 11. Controller contract

The controller reads:

- immutable objective
- frozen acceptance criteria
- current canonical Run state
- fresh reconciliation report
- progress records
- verification evidence
- policy state
- budgets
- failure/recovery state
- human-control state

The controller may emit:

- structured Intent proposals
- recovery decisions
- pause/wait decisions
- escalation requests
- completion proposals

The controller MUST NOT:

- execute commands directly
- bypass Policy
- mutate files directly
- accept model self-report as verification
- change acceptance criteria silently
- ignore a stale reconciliation report
- continue after a hard budget/authority stop
- treat historical state as current reality

## 12. Human authority

`WAITING_HUMAN` is a durable state, not a timeout.

While waiting for human authority:

- autonomous continuation is prohibited;
- workers cannot self-authorize continuation;
- the controller cannot convert the state back to active execution without the defined authority event;
- emergency abort remains available as a higher-priority human control.

## 13. Budget and termination boundary

Budgets are hard safety constraints, not optimization hints.

At minimum the controller must account for:

- wall-clock runtime
- attempts
- model calls
- commands
- output/evidence growth
- worker runtime
- persistent resource growth where measured

Budget exhaustion MUST prevent autonomous continuation even if the model requests another attempt.

Controller failure must not remove the termination boundary; enforcement therefore belongs below the controller where practical.

## 14. Anti-loop boundary

Phase 7 MUST provide a deterministic minimum anti-loop mechanism using existing progress/fingerprint foundations.

A loop candidate may consider:

- repeated intent identity
- repeated operation identity
- repeated artifact digest
- repeated verification state
- repeated reconciliation state
- repeated failure signature
- bounded strategy diversity

Semantic novelty scoring and advanced entropy research are NOT required for the first controller implementation.

A loop decision must be explainable from durable observations.

## 15. Context boundary

The model receives a bounded Context Bundle rather than unrestricted repository state.

Each context item must carry provenance sufficient to identify its source and freshness.

Context is informational and untrusted. Prompt injection or repository instructions cannot grant authority.

The initial Context Engine may remain deterministic and lexical/structural. Embeddings, RLM, and advanced recursive context strategies remain research tracks until validated.

## 16. Phase 7 implementation order

The implementation sequence is frozen as:

### 7.0 Safety foundation contracts

Implement and test the schemas/contracts for:

- AcceptanceCriteria
- ProgressRecord
- ProgressPredicate
- CompletionPredicate
- OperationIdentity
- ReconciliationReport
- WorktreeContract
- EvidenceLink

### 7.1 Reality and workspace primitives

Implement minimal worktree ownership and reconciliation support required for controller decisions.

### 7.2 Acceptance and progress integration

Compile/freeze acceptance criteria and connect progress to verification evidence.

### 7.3 Idempotency and effect identity

Insert operation identity at the execution boundary without weakening Policy -> Broker -> Backend authority.

### 7.4 Transition authority

Make autonomous state transitions controller/recovery-authority owned and reject bypasses.

### 7.5 Controller

Implement the first deterministic Controller against the frozen contracts.

### 7.6 Anti-loop, budgets, escalation

Integrate existing recovery/budget foundations with durable controller decisions and hard stops.

### 7.7 Controller gate

Only after all preceding pieces pass their tests may the autonomous loop be enabled.

## 17. Mandatory tests before autonomous loop

The following are mandatory:

1. stale reconciliation report rejected;
2. conflicting Git/filesystem state produces anomaly;
3. completion without independent verification rejected;
4. modified acceptance criteria rejected;
5. worker cannot mutate acceptance criteria;
6. duplicate operation delivery produces zero additional logical effects where idempotency is supported;
7. fencing race rejects stale worker effect;
8. Policy denial cannot be bypassed by controller;
9. controller cannot bypass Broker;
10. controller cannot transition from WAITING_HUMAN without authority;
11. hard budget stop survives controller restart;
12. controller restart/replay is deterministic;
13. repeated intent/artifact/verification cycle is bounded;
14. evidence references remain valid across restart;
15. verifier cannot certify a stale artifact;
16. worktree ownership prevents cross-Run mutation;
17. sandbox remains the security boundary;
18. recovery reconciles external reality before retry.

## 18. Chaos begins early

Chaos testing is not postponed until a late long-run phase.

Once the controller exists, inject at least:

- worker death
- controller restart
- duplicate result
- stale worker result
- network loss
- verifier failure
- filesystem mutation
- Git mutation outside expected operation
- lease expiration
- process timeout
- budget exhaustion
- human pause/revoke

The purpose is to validate the architecture continuously, not merely to produce a final benchmark.

## 19. Explicitly deferred research

These do not become Phase 7 requirements without evidence:

- RLM as core execution mechanism
- λ-RLM runtime
- vector database
- looped Transformer architecture
- semantic entropy monitor
- ALDG or other advanced loop algorithms
- autonomous skill mutation
- multi-agent swarm
- Kubernetes/distributed scheduler
- Telegram control surface
- broad provider routing
- cryptographic signing infrastructure beyond what integrity requirements actually justify

Research proposals must be evaluated against VAJRA's architectural laws and falsifiable tests.

## 20. Gate F — Autonomous Controller Safety Gate

Gate F passes only when:

```text
frozen acceptance
AND
fresh reconciliation
AND
workspace ownership
AND
operation identity/idempotency
AND
policy/broker authority
AND
independent verification
AND
evidence-linked progress
AND
hard termination
AND
human escalation
AND
deterministic recovery/replay
AND
anti-loop protection
```

are all demonstrated by executable tests.

The first autonomous Run must remain bounded and single-Run/single-active-worker until concurrency is independently certified.

## 21. Definition of Phase 7 completion

Phase 7 is complete when VAJRA can:

1. accept a bounded engineering objective;
2. freeze machine-checkable acceptance criteria;
3. establish an owned workspace;
4. observe and reconcile current reality;
5. provide bounded trusted/provenance-tagged context to a model;
6. receive a structured intent rather than an execution instruction;
7. authorize the intent through Policy;
8. execute through the Broker and security boundary;
9. identify effectful operations idempotently;
10. verify the resulting artifact independently;
11. record integrity-linked evidence;
12. determine measurable progress;
13. detect bounded non-progress;
14. enforce hard budgets;
15. survive worker/controller restart;
16. escalate to a human durably when required;
17. propose completion only when all completion predicates hold;
18. leave canonical state consistent with reconciled external reality.

## 22. Freeze rule

No Phase 10 autonomous engineering loop is permitted to become the architectural excuse for weakening any contract above.

If implementation pressure conflicts with a frozen contract, the contract is revisited explicitly through a design decision; it is not silently bypassed.

**Phase 7 implementation begins only after this document and the corresponding executable contract tests are accepted as the design baseline.**
