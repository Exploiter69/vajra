# VAJRA v1 — Architecture & Roadmap Specification

**Project:** VAJRA  
**Document:** Post-Phase 6 Architecture, Safety Invariants, and Roadmap Specification  
**Status:** Architecture freeze candidate — implementation begins only after the Phase 7 design gate passes  
**Supersedes for forward development:** `docs/VAJRA_v0_Technical_Specification.txt`  
**Current implementation baseline:** Phase 6 complete; 419 tests passed at the audit checkpoint  
**Primary constraint:** ₹0.00 operating cost

---

## 1. Purpose

This document defines the forward-looking architecture VAJRA must follow after completion of the durable execution substrate and through the autonomous-engineering roadmap.

The original v0 specification established the durable Engineering Run, execution authority boundary, worker model, policy, verification, sandbox, context, and human-control foundations. This document extends those foundations with the control-and-truth architecture required for reliable autonomous engineering.

This document is normative where it says **MUST**, **MUST NOT**, **SHOULD**, or **MAY**.

It is derived from:

1. the original VAJRA v0 specification;
2. the implemented Phase 6 substrate;
3. the post-Phase-6 roadmap;
4. four independent adversarial research reviews;
5. the VAJRA architectural laws; and
6. the absolute ₹0.00 operating-cost constraint.

Research proposals are not automatically architecture. A proposal becomes part of VAJRA only when it is compatible with the laws, supported by evidence, and justified by a gate.

---

## 2. System Definition

VAJRA is a **durable autonomous engineering runtime** that accepts an engineering objective and attempts to produce a verified engineering artifact while preserving canonical state across failures of workers, models, processes, networks, and machines.

VAJRA is not primarily:

- a chatbot;
- an LLM wrapper;
- an IDE;
- a shell agent;
- a single autonomous model;
- a Telegram bot;
- a model-hosting platform;
- a generic agent framework;
- a multi-agent swarm; or
- a collection of shell scripts.

The fundamental object is the **Engineering Run**, not the model session.

The fundamental guarantee remains:

> A worker, model, process, network connection, or machine may disappear without destroying the Engineering Run.

The stronger post-Phase-6 guarantee is:

> VAJRA must not treat durable claims, model output, worker output, or historical state as current engineering truth without reconciling and independently verifying the relevant reality.

---

## 3. Primary Objective

> Produce useful, verified engineering progress while the human owner is away, with minimal human intervention and no unsafe surprises.

VAJRA optimizes for **verified progress**, not model activity, token consumption, number of patches, or apparent task completion.

---

## 4. Non-Negotiable Constraints

### 4.1 Zero cost

VAJRA development and normal operation MUST preserve the ₹0.00 operating-cost constraint.

The architecture MUST NOT depend on paid model APIs, paid hosted databases, paid queues, paid orchestration services, mandatory paid cloud infrastructure, pay-as-you-go inference, paid observability platforms, or credit-card-gated infrastructure.

Free/open-source or genuinely free external infrastructure MAY be used when independently validated and when VAJRA remains architecturally independent of it.

### 4.2 Model independence

No model, vendor, API, GPU, or inference provider is authoritative.

### 4.3 Human authority

Human authority is never delegated to a model, worker, memory system, verifier, or external control surface.

### 4.4 Evidence over claims

Engineering progress requires independently generated evidence.

### 4.5 Durable state over sessions

A model conversation is disposable. An Engineering Run is durable.

---

# 5. Architectural Laws

The original ten laws remain permanent. Six laws formalize the post-Phase-6 control layer.

## Law 1 — Model Is Not Authority

A model may propose actions. A model MUST NOT directly authorize or execute them.

```text
Model
  ↓
Intent
  ↓
Policy
  ↓
Execution Broker
  ↓
Actual operation
```

## Law 2 — VAJRA Owns Canonical State

Models, workers, model sessions, caches, repository text, external services, and control surfaces are not canonical VAJRA state stores.

## Law 3 — Meaningful Operations Are Durable

Planning, model invocation, intent creation, authorization, execution, verification, worker assignment, retry, recovery, human approval, promotion, and terminal decisions MUST have durable representations where they affect Run semantics.

## Law 4 — Reasoning Cannot Directly Execute

Reasoning produces structured proposals. It does not directly execute shell commands, Git operations, filesystem mutations, credential access, or external side effects.

## Law 5 — Worktree Isolation Is Not Security Isolation

A Git worktree is a workspace mechanism. It is not a kernel, network, credential, process, or sandbox security boundary.

## Law 6 — Verification Is External

Model confidence and worker self-report are not completion evidence.

## Law 7 — Failure Is Data

Failures MUST be durable, classifiable, and usable for recovery without becoming automatically trusted instructions.

## Law 8 — Autonomy Is Bounded

Every Run has explicit time, step, attempt, model, execution, resource, scope, and termination limits.

## Law 9 — Progress Requires Evidence

Only verified artifact state satisfying a machine-checkable progress predicate constitutes engineering progress.

## Law 10 — Human Is Ultimate Authority

Human-required decisions become durable control boundaries.

## Law 11 — Fresh Reality Before Autonomous Decision

Before an autonomous Controller advances a Run based on mutable external state, VAJRA MUST obtain a fresh reconciliation of the relevant state.

## Law 12 — Evidence-Bound Progress

A progress or completion transition MUST reference machine-checkable evidence linked to the operation, artifact, workspace, and verification context that produced it.

## Law 13 — No Ambiguous Continuation

If durable state and observed external state cannot be reconciled deterministically, VAJRA MUST stop, recover conservatively, or enter `WAITING_HUMAN`. It MUST NOT guess and continue.

## Law 14 — Operation Identity

Every meaningful mutable operation MUST have a durable identity sufficient to detect replay, stale execution, and conflicting effects within VAJRA's control boundary.

## Law 15 — Controller Cannot Bypass Authority

The Controller decides lifecycle progression. It does not bypass Policy, the Execution Broker, the sandbox, verification, budgets, or human gates.

## Law 16 — Historical Information Is Not Current Truth

History, memory, prior evidence, worker claims, and model output may inform reasoning, but newly observed authoritative state supersedes them when they conflict.

---

# 6. System Architecture

```text
                         HUMAN
                           │
                    objective / approval
                           │
                           ▼
                 ┌───────────────────┐
                 │   CONTROL PLANE   │
                 │ CLI / future API  │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │    RUN PLANE      │
                 │ Run/Step/Attempt  │
                 │ events/progress   │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │    CONTROLLER     │
                 │ lifecycle/truth   │
                 └───┬─────┬─────┬───┘
                     │     │     │
                     ▼     ▼     ▼
                  TRUTH PROGRESS CONTEXT
                  ENGINE  ENGINE  ENGINE
                     │     │     │
                     └─────┼─────┘
                           ▼
                       REASONING
                           │
                       proposes
                           ▼
                         INTENT
                           │
                         POLICY
                           │
                           ▼
                   EXECUTION BROKER
                           │
                    RESOURCE/SANDBOX
                           │
                           ▼
                       ARTIFACT
                           │
                    INDEPENDENT VERIFY
                           │
                           ▼
                        EVIDENCE
                           │
                           └────────────► Controller
```

### 6.1 Control Plane

Owns human interaction and administrative commands. It does not own Run truth independently from the Run plane.

### 6.2 Run Plane

Owns durable Run state, Steps, Attempts, lifecycle state, event history, budgets, checkpoints, and durable references.

### 6.3 Controller

Owns autonomous lifecycle decisions and legal state transitions. It consumes fresh reconciliation, progress, verification evidence, budgets, and policy state.

### 6.4 Reasoning Plane

Produces plans, intents, analysis, and proposed next actions. It is disposable and untrusted.

### 6.5 Policy Plane

Deterministically authorizes, denies, modifies, or escalates proposed operations.

### 6.6 Execution Plane

Converts authorized operations into real effects through the Execution Broker and sandbox/resource boundaries.

### 6.7 Verification/Evidence Plane

Independently determines whether observable engineering predicates are satisfied and records structured evidence.

### 6.8 Context/Truth Plane

Builds bounded context from current repository/workspace state and reconciles durable claims with observed state.

---

# 7. Canonical Data Model

## 7.1 EngineeringRun

```text
EngineeringRun
├── run_id
├── created_at
├── updated_at
├── objective
├── repository_id
├── repository_url
├── base_revision
├── acceptance_criteria
├── policy_id
├── policy_version
├── budget_id
├── state
├── workspace_id
├── current_step_id
├── created_by
├── final_disposition
├── progress_summary
└── current_reconciliation_ref
```

## 7.2 Step

```text
Step
├── step_id
├── run_id
├── name
├── objective
├── status
├── current_attempt_id
├── progress_refs
├── verification_refs
└── recovery_refs
```

A Step is durable and represents an intended unit of engineering progress.

## 7.3 Attempt

```text
Attempt
├── attempt_id
├── run_id
├── step_id
├── worker_id
├── model_id
├── model_version
├── started_at
├── finished_at
├── status
├── input_context_digest
├── output_digest
├── usage
├── errors
├── artifact_refs
└── verification_refs
```

An Attempt is disposable. Attempt death MUST NOT destroy the Run.

```text
Attempt → FAILED
Step    → RECOVERING
Step    → replacement Attempt
Run     → survives
```

---

# 8. Run State Machine

Primary lifecycle:

```text
CREATED
  ↓
QUEUED
  ↓
ORIENTING
  ↓
PLANNING
  ↓
EXECUTING
  ↓
VERIFYING
  ↓
CANDIDATE
  ↓
PROMOTION
  ↓
COMPLETE
```

Exceptional states:

```text
RECOVERING
PAUSED
WAITING_HUMAN
FAILED
ABORTED
EXPIRED
```

Only the Controller/Run state authority may commit lifecycle transitions.

The model MUST NOT invent lifecycle states. The worker MUST NOT promote a Run. The verifier MUST NOT directly change Run state.

`EXECUTING → COMPLETE` is invalid.

Completion requires at minimum:

```text
objective
+ frozen acceptance criteria
+ current artifact/repository state
+ independent verification evidence
+ progress/completion predicate
+ policy authorization
```

`WAITING_HUMAN` is a durable boundary. Model output cannot automatically escape it.

---

# 9. Controller Contract

The Controller answers:

> Given everything that has happened and the current observed reality, what is the next legal action for this Run?

## 9.1 Inputs

The Controller MAY consume:

- canonical Run state;
- Step/Attempt state;
- fresh `ReconciliationReport`;
- `ProgressRecord` history;
- verification evidence;
- failure classifications;
- budgets;
- lease state;
- policy decisions;
- human decisions;
- context references;
- model proposals.

## 9.2 Outputs

```text
START_STEP
CREATE_ATTEMPT
REQUEST_CONTEXT
REQUEST_PLAN
EXECUTE_INTENT
REQUEST_VERIFICATION
RETRY
CHANGE_STRATEGY
CHANGE_MODEL
CHANGE_WORKER
RESTORE_CHECKPOINT
WAITING_HUMAN
PAUSE
ABORT
COMPLETE
FAIL
EXPIRE
```

Every executable operation remains:

```text
Controller
  ↓
Intent
  ↓
Policy
  ↓
Execution Broker
```

The Controller MUST NOT advance based solely on model claims, worker claims, old events, stale reconciliation, historical memory, unverified artifacts, or mutable acceptance criteria.

---

# 10. Truth and Reconciliation

Durable state is durable **state**, not automatically physical truth.

| Fact | Primary authority |
|---|---|
| Run lifecycle | VAJRA durable state |
| Step/Attempt identity | VAJRA durable state |
| Policy version | VAJRA durable state |
| Budget accounting | VAJRA state + measured execution |
| Current files | actual workspace/filesystem |
| Repository revision | Git |
| Verification result | independent verifier |
| Model proposal | model output, untrusted |
| Worker claim | worker output, untrusted |
| Historical event | event history/audit input |
| Historical memory | informational only |

## 10.1 ReconciliationReport

```text
ReconciliationReport
├── report_id
├── run_id
├── generated_at
├── durable_state_digest
├── workspace_id
├── workspace_state
├── git_revision
├── git_status_digest
├── filesystem_digest
├── checkpoint_ref
├── active_lease_state
├── verification_state
├── budget_state
├── observed_external_state
├── divergence_class
├── severity
├── freshness
└── disposition
```

Possible dispositions:

```text
CONSISTENT
RECOVERABLE
REVERIFY
RECOVERING
WAITING_HUMAN
ABORT
```

`UNKNOWN` or ambiguous divergence MUST NOT be treated as consistency.

## 10.2 Mandatory reconciliation points

Fresh reconciliation is required before autonomous decisions involving mutable reality, including recovery, promotion, completion, checkpoint restore, retry after uncertain execution, budget-sensitive execution, workspace ownership changes, acceptance evaluation, and stale-worker resolution.

## 10.3 Recovery

```text
failure
  ↓
RECOVERING
  ↓
observe current reality
  ↓
reconcile
  ↓
resume / retry / rollback / human / abort
```

---

# 11. Progress Model

Progress is not activity.

## 11.1 ProgressRecord

```text
ProgressRecord
├── progress_id
├── run_id
├── step_id
├── attempt_id
├── intent_id
├── operation_identity
├── pre_state_digest
├── post_state_digest
├── artifact_refs
├── verification_refs
├── predicate_id
├── predicate_version
├── predicate_result
├── novelty_fingerprint
├── failure_signature
└── created_at
```

## 11.2 Progress predicate

A progress predicate answers:

- What changed?
- Was it relevant to the objective?
- Was the resulting artifact observed?
- Was it independently verified?
- What remains unresolved?

Repeated activity without a material state/evidence change is not progress.

---

# 12. Acceptance and Completion

Acceptance criteria are protected inputs to autonomous control.

```text
AcceptanceCriteria
├── criteria_id
├── version
├── objective_digest
├── predicates
├── required_evidence
├── verification_plan_ref
├── integrity_digest
├── created_at
└── frozen_at
```

Acceptance criteria MUST be frozen before autonomous implementation that depends on them.

The model MUST NOT rewrite acceptance criteria to make a failing artifact pass.

A human-approved scope change creates a new version and durable decision.

```text
CompletionPredicate(
    objective,
    frozen_acceptance,
    current_artifact,
    current_repository_state,
    verification_evidence,
    policy
)
→ TRUE | FALSE | INCONCLUSIVE
```

`INCONCLUSIVE` MUST NOT become `COMPLETE`.

---

# 13. Operation Identity and Idempotency

Every meaningful mutable operation receives a durable identity.

```text
OperationIdentity
├── operation_id
├── run_id
├── step_id
├── attempt_id
├── intent_id
├── operation_type
├── parameters_digest
├── target_resource
├── idempotency_key
└── created_at
```

Before a mutable broker operation:

```text
fresh reconciliation
  ↓
budget check
  ↓
lease/fencing check
  ↓
idempotency check
  ↓
policy authorization
  ↓
Execution Broker
```

Replay of an already committed VAJRA-controlled operation MUST return the prior durable result or equivalent no-op rather than duplicate the effect.

VAJRA cannot make an arbitrary third-party system idempotent if that system provides no idempotency mechanism. External effects therefore require provider idempotency, deterministic duplicate detection, compensating operations, or human authorization.

---

# 14. Worker Leasing and Fencing

The Phase 6 worker protocol remains the foundation.

```text
WorkerExecutionIdentity
├── run_id
├── step_id
├── attempt_id
├── worker_id
├── lease_id
├── fencing_token
└── correlation_id
```

A worker with an expired or superseded lease MUST NOT commit canonical results or protected mutable effects.

As concurrency expands, fencing MUST cover relevant mutable resources, including workspace ownership, Git mutation, filesystem mutation, resource reservations, and protected external effects where applicable.

Worker output is evidence input, not automatically proof.

---

# 15. Workspace Architecture

Each unattended Run receives a VAJRA-owned workspace.

```text
repository
├── main
├── vajra-run-A
├── vajra-run-B
└── ...
```

```text
Workspace
├── workspace_id
├── run_id
├── repository_id
├── base_revision
├── path
├── owner_lease
├── status
├── git_state
├── cleanup_state
└── resource_allocations
```

Lifecycle:

```text
ALLOCATE
  ↓
INITIALIZE
  ↓
OWN
  ↓
USE
  ↓
CHECKPOINT / RECONCILE
  ↓
RELEASE
  ↓
CLEANUP
```

Unattended VAJRA coding MUST NOT modify the human's active development worktree.

VAJRA MUST explicitly serialize conflicting repository-management operations rather than assuming worktrees eliminate shared-resource contention. The exact locking strategy must be experimentally validated before multi-run concurrency is enabled.

---

# 16. Resource Isolation

Worktree isolation does not isolate:

- CPU;
- memory;
- disk;
- processes;
- network;
- ports;
- temporary directories;
- package/build caches;
- local databases;
- environment variables.

Until concurrency is explicitly enabled and gated, the supported local execution mode SHOULD remain one active engineering worker/run.

When concurrency is introduced:

```text
Run → ResourceAllocation
       ├── tmp_dir
       ├── cache_dirs
       ├── port_range
       ├── process_limit
       └── resource_limits
```

Resource allocation is a VAJRA responsibility, not a model responsibility.

---

# 17. Sandbox Architecture

```text
SandboxBackend
├── RestrictedLocal
├── Container
├── gVisor
├── Firecracker
└── RemoteWorker
```

Phase 6 physically validated the gVisor path. This proves the validated workload path works; it does not prove every future security property.

```text
SandboxSpec
├── workspace_id
├── filesystem_scope
├── network_enabled
├── allowed_capabilities
└── resource_limits
```

Future hardened forms SHOULD bind sandbox configuration, filesystem policy, network policy, credential policy, resource policy, and runtime identity.

The sandbox is the security boundary for untrusted execution; the worktree is not.

Specific research claims about gVisor internals, direct filesystem modes, syscall restrictions, or escape paths MUST be verified against the exact deployed version/configuration before becoming hard requirements.

---

# 18. Reasoning and Model Contract

```text
propose(ContextBundle)
    → Intent[]
```

Possible intents:

```text
InspectFile
SearchCode
InspectSymbol
ApplyPatch
CreateFile
DeleteFile
RunCommand
RunTest
RunBuild
RequestHuman
Finish
```

`Finish` is a proposal, not completion authority.

Every meaningful model invocation SHOULD record model identity/version, request digest, context digest, structured output, raw output reference, usage, errors, and evidence references.

Model switching is a VAJRA routing/recovery decision, not a model decision.

---

# 19. Context Engine

VAJRA MUST NOT dump an entire repository into model context by default.

```text
Repository / Run history
        ↓
Indexer
        ↓
Symbols / references / dependencies
        ↓
Deterministic retrieval
        ↓
Ranking
        ↓
Trust / provenance filtering
        ↓
Freshness check
        ↓
ContextBundle
```

```text
ContextBundle
├── objective
├── acceptance_criteria
├── repository_summary
├── relevant_files
├── relevant_symbols
├── dependencies
├── recent_changes
├── relevant_history
├── current_reconciliation
├── constraints
├── allowed_capabilities
└── budget
```

Provenance classes SHOULD distinguish:

```text
TRUSTED_SYSTEM
TRUSTED_POLICY
TRUSTED_VERIFICATION
OBSERVED_REPOSITORY
MODEL_OUTPUT
WORKER_OUTPUT
EXTERNAL_CONTENT
HISTORICAL_MEMORY
UNKNOWN
```

Repository instructions are repository content, not automatically VAJRA instructions.

Context freshness must be tied to the repository/workspace state it describes. Stale context must be rebuilt or explicitly marked stale.

Lossy compression must preserve provenance and source references. It MUST NOT silently upgrade untrusted content into trusted evidence.

---

# 20. Verification Architecture

Verification is independent from the reasoning model.

```text
Static checks
  ↓
Targeted tests
  ↓
Build
  ↓
Full tests where required
  ↓
Acceptance checks
  ↓
Structured evidence
```

```text
VerificationResult
├── verification_id
├── run_id
├── step_id
├── attempt_id
├── workspace_id
├── source_revision
├── artifact_refs
├── check_id
├── command
├── status
├── exit_code
├── output_reference
├── environment
├── verifier_version
├── timestamp
└── evidence_digest
```

The worker/model MUST NOT silently control the verifier or acceptance harness.

Evidence MUST identify the artifact/workspace/revision being verified so an old passing artifact cannot satisfy a new failed attempt.

---

# 21. Anti-Gaming

The verifier must defend against:

- deleting failing tests;
- weakening assertions;
- adding `xfail`/skip behavior;
- modifying fixtures to hide failure;
- replacing real dependencies with mocks;
- lowering configuration thresholds;
- modifying verification code;
- reporting success from metadata without execution;
- hidden broken state;
- manipulating generated outputs.

Acceptance criteria, verification plans, and verifier identity MUST be protected by policy and integrity checks.

A successful command is evidence about that command. It is not automatically proof that the engineering objective is satisfied.

Phase 9 must include deliberate verification-gaming and stale-artifact tests.

---

# 22. Failure and Recovery

The Phase 6 failure substrate remains:

```text
Failure
  ↓
Classifier
  ↓
Recovery Policy
  ↓
Action
```

Actions:

```text
RETRY
NEW_STRATEGY
CHANGE_MODEL
CHANGE_WORKER
RESTORE_CHECKPOINT
REQUEST_HUMAN
ABORT
```

Controller-level failure classes add:

```text
STATE_DIVERGENCE
NO_PROGRESS
LOOP_DETECTED
STALE_CONTEXT
STALE_WORKER
VERIFICATION_INTEGRITY_FAILURE
ACCEPTANCE_INVALID
BUDGET_EXHAUSTION
RESOURCE_CONTENTION
UNKNOWN_DIVERGENCE
```

Failure output is data, not executable policy.

---

# 23. Anti-Loop Architecture

Hard budgets prevent infinite execution but do not identify semantic oscillation early.

A `ProgressFingerprint` MAY combine:

```text
intent identity
operation identity
artifact digest
verification-state vector
failure signature
repository state
```

Example:

```text
Patch A → failure X
Patch B → failure Y
Patch A → failure X
Patch B → failure Y
```

If the sequence repeats without material progress, the Controller MUST escalate, change strategy, or terminate according to policy before uncontrolled budget exhaustion.

Agentic Loop Dependence Graphs and model-specific entropy techniques are research/optimization tracks, not fundamental safety requirements.

---

# 24. Budgets and Termination

Minimum durable budgets:

```text
max_runtime
max_steps
max_attempts
max_model_calls
max_command_count
max_output_size
max_worker_runtime
```

Future:

```text
max_network_bytes
max_disk_usage
max_model_tokens
max_parallel_workers
max_context_size
max_evidence_storage
```

Budgets MUST be checked before and after relevant operations and recorded durably.

Budget exhaustion MUST produce a durable transition.

Termination MUST NOT depend solely on the correctness of the model/controller loop. Runtime-enforceable limits must remain in the substrate.

---

# 25. Checkpoints

```text
Checkpoint
├── checkpoint_id
├── run_id
├── step_id
├── event_position
├── git_revision
├── workspace_identity
├── policy_version
├── state_digest
├── progress_refs
└── evidence_refs
```

Git alone is not a complete checkpoint because untracked files and external state may escape Git history.

Checkpoint restore MUST be followed by reconciliation and verification as appropriate.

---

# 26. Event History

Events remain append-oriented and audit-oriented.

Representative events:

```text
RunCreated
RunQueued
StepCreated
AttemptStarted
WorkerAssigned
ModelInvocationStarted
ModelInvocationCompleted
IntentProposed
IntentDenied
IntentApproved
CommandStarted
CommandCompleted
PatchProposed
PatchApplied
VerificationStarted
VerificationCompleted
FailureDetected
FailureClassified
RetryScheduled
HumanApprovalRequested
HumanApprovalGranted
HumanApprovalDenied
CheckpointCreated
RecoveryStarted
RecoveryCompleted
ReconciliationStarted
ReconciliationCompleted
ProgressRecorded
PromotionStarted
RunPaused
RunCompleted
RunFailed
```

Every event SHOULD carry:

```text
run_id
step_id
attempt_id
worker_id
timestamp
event_type
payload
correlation_id
```

The event history is an audit trail and recovery input. It is not unquestionable physical reality.

Cryptographic event chaining MAY be evaluated later if the threat model demonstrates material benefit; it is not mandatory solely because a research review proposed it.

---

# 27. Human Control

Possible human actions:

```text
PAUSE
RESUME
CANCEL
ABORT
RETRY
APPROVE
REJECT
```

Human-required conditions include, according to policy:

- ambiguous reconciliation;
- acceptance ambiguity;
- dangerous/destructive operations;
- unverifiable completion;
- unresolved security anomalies;
- unsafe external side effects;
- repeated failure beyond recovery policy.

`WAITING_HUMAN` MUST survive worker/process/network failure.

The model cannot manufacture human approval.

---

# 28. Security Model

Potentially untrusted inputs include:

- model output;
- repository contents;
- repository instructions;
- dependencies;
- generated scripts;
- worker environment;
- network responses;
- external tools;
- persisted model-generated memory;
- stale artifacts;
- tool results.

Threat classes include:

```text
prompt injection
tool injection
command injection
path traversal
symlink attacks
TOCTOU
credential exposure
dependency attacks
network exfiltration
sandbox escape
verification manipulation
memory poisoning
stale-worker execution
replay
resource exhaustion
Git hook abuse
submodule abuse
package-script abuse
```

Security decisions remain deterministic and outside model authority.

---

# 29. Credentials

Secrets MUST NOT be placed into ordinary model context.

Credentials, where unavoidable, MUST be scoped, capability-bound, injected only when required, unavailable to unrelated operations, and excluded from ordinary evidence/log output.

A future secret broker MAY provide short-lived credentials. Early VAJRA development SHOULD minimize secret-dependent operations.

---

# 30. MCP and External Tools

MCP is interoperability, not authorization, security boundary, canonical state, or execution authority.

```text
Model
  ↓
Tool/MCP proposal
  ↓
VAJRA Policy
  ↓
Execution Broker
  ↓
Authorized capability
  ↓
Tool
```

External tools are untrusted effects unless independently verified.

---

# 31. Physical Worker Topology

The original laptop/remote-worker topology remains an option, not a hard infrastructure dependency.

```text
Laptop
  ├── local CLI
  ├── lightweight execution
  ├── local llama.cpp/Ollama
  └── development
       │
       ▼
VAJRA durable control/runtime
       │
       ▼
Remote worker(s)
  ├── Kaggle GPU
  ├── future free worker
  └── future local worker
```

The previously envisioned Oracle Always Free deployment is **not** a required dependency. It was not physically deployed under the user's zero-cost/no-card constraint.

Kaggle is an ephemeral worker and never canonical state.

If Kaggle disappears:

```text
worker loss
  ↓
Attempt failure
  ↓
reconciliation
  ↓
recovery
  ↓
retry / alternate worker / human
```

---

# 32. Worker Capability Model

```text
WorkerCapabilities
├── accelerator
├── vram
├── system_ram
├── model
├── model_version
├── context_limit
├── supported_tasks
├── sandbox_type
└── network_policy
```

Future routing MAY consider task complexity, capability fit, reliability, latency, compatibility, and budget.

Routing never changes the authority boundary.

---

# 33. Observability

A Run should answer:

```text
What happened?
Why did it happen?
Which model proposed it?
Which policy allowed it?
Which worker executed it?
Which workspace was used?
What changed?
What failed?
Why was recovery selected?
Why was the model/worker changed?
What evidence proves progress?
Why did VAJRA stop?
```

Observability is not a substitute for verification or reconciliation.

---

# 34. History and Memory

The v0 principle remains:

> History first. Memory later.

Initial durable information:

```text
Run history
events
artifacts
verification evidence
failure history
structured decisions
repository state
reconciliation reports
progress records
```

Future Engineering Memory may add failure memory, repository memory, context memory, and conflict awareness.

Memory is informational. It never grants permission. Current observed truth outranks historical memory.

---

# 35. Research Tracks — Not Foundation Dependencies

## 35.1 Retrieval

Benchmark deterministic retrieval, lexical/BM25, embeddings, hybrid retrieval, and graph-assisted retrieval before selecting a production strategy.

## 35.2 RLM / λ-RLM

Research recursive context exploration only inside a bounded VAJRA-controlled context interface. Model-generated arbitrary REPL code must not become execution authority.

## 35.3 Looped Transformers

Model architecture research. It does not change VAJRA's runtime authority model.

## 35.4 Entropy monitoring

Long-horizon context degradation is a valid research topic, but an entropy score is not a safety primitive until it has a falsifiable definition and gate.

## 35.5 ALDG

Potential loop-prediction optimization. It is not a replacement for budgets, progress predicates, reconciliation, and termination authority.

## 35.6 Skill differential execution

Interesting future research for measuring procedural-skill effects. Not a core runtime dependency.

## 35.7 Cryptographic attestations

May be evaluated where they materially improve evidence integrity. Not mandatory for every event by default.

---

# 36. Rejected Architectural Foundations

The following are explicitly rejected as foundations:

- Telegram-first control;
- vector-database-first memory;
- RLM-first architecture;
- looped-transformer dependency;
- Kubernetes without demonstrated need;
- generic agent frameworks as runtime authority;
- multi-agent swarm before reliable single-run autonomy;
- autonomous security-policy modification;
- model-generated arbitrary Python as privileged authority;
- worker self-report as proof;
- event log as unquestionable reality;
- Oracle as mandatory dependency;
- paid infrastructure or paid inference;
- model authority over Policy;
- model authority over verification;
- memory authority over current state;
- autonomous bypass of `WAITING_HUMAN`.

---

# 37. Roadmap Overview

```text
PHASE 6 — Durable Execution Substrate
                │
                ▼
PHASE 7 — Autonomous Control Foundation
                │
                ├── truth/reconciliation
                ├── progress/completion predicates
                ├── operation identity/idempotency
                ├── workspace ownership primitives
                ├── resource isolation primitives
                ├── Controller
                ├── anti-loop
                ├── hard termination
                └── human authority
                │
                ▼
PHASE 7 SAFETY GATE
                │
                ▼
PHASE 8 — Context Engine
                │
                ▼
PHASE 9 — Verification + Anti-Gaming
                │
                ▼
PHASE 10 — Real Autonomous Engineering Loop
                │
                ▼
PHASE 11 — Chaos + Long-Run Reliability
                │
                ▼
PHASE 12 — Model / Worker Routing
                │
                ▼
PHASE 13 — Always-On Control Plane
                │
                ▼
PHASE 14 — Engineering Memory
                │
                ▼
PHASE 15 — Production Hardening
                │
                ▼
PHASE 16 — Advanced Autonomy
                │
                ▼
PHASE 17 — Controlled Self-Improvement
                │
                ▼
PHASE 18+ — Research / Long Horizon
```

Phase names are roadmap boundaries. Some primitives intentionally land before the phase in which their full feature set is completed.

---

# 38. Phase 6 — Durable Execution Substrate

**Status: COMPLETE**

Completed:

- core domain contracts;
- Engineering Run lifecycle;
- durable runtime;
- worker protocol;
- policy engine;
- execution broker;
- verification;
- failure/recovery;
- CLI;
- physical worker transport / Gate C;
- sandbox / Gate D.

Baseline checkpoint:

```text
419 tests passed
compileall PASS
git diff --check PASS
working tree clean
```

Phase 6 is the substrate baseline. New work belongs to later phases unless an audit identifies a correctness blocker.

---

# 39. Phase 7 — Autonomous Control Foundation

Phase 7 is the next implementation target and the highest-risk architectural phase.

## 7A — Truth/Reconciliation Contracts

Implement `ReconciliationReport`, divergence classes, authority mapping, freshness semantics, recovery reconciliation, and deterministic conflict dispositions.

## 7B — Progress and Completion Model

Implement/freeze `ProgressRecord`, `ProgressPredicate`, `CompletionPredicate`, acceptance schema, and evidence linkage.

## 7C — Operation Identity and Idempotency

Implement operation identity, idempotency-key derivation, replay detection, and duplicate-effect handling within VAJRA's control boundary.

## 7D — Workspace Ownership

Implement the minimal VAJRA-owned workspace lifecycle needed by the Controller and reconciliation engine.

## 7E — Resource Isolation Primitives

Implement only the resource controls required by the supported execution mode. Avoid a general distributed scheduler until concurrency is needed.

## 7F — Run Controller

Implement deterministic Controller decisions over canonical state and evidence.

## 7G — Anti-Loop / No-Progress Detection

Implement observable fingerprints and bounded escalation.

## 7H — Hard Budgets and Termination

Make budgets runtime-enforced and durable.

## 7I — Human Escalation

Make human boundaries explicit, durable, and non-bypassable by model output.

---

# 40. Phase 7 Safety Gate — Controller Safety Gate

No autonomous engineering loop may be enabled until this gate passes.

### G1 — Legal transitions

No illegal state transition can be produced by model output.

### G2 — Completion integrity

No Run can become `COMPLETE` without frozen acceptance, current artifact/repository state, required verification evidence, progress/completion predicate, and policy authorization.

### G3 — Reconciliation

Injected state divergence produces deterministic recovery or `WAITING_HUMAN`, never silent continuation.

### G4 — Restart

Kill/restart at decision boundaries produces equivalent safe recovery.

### G5 — Replay

Repeated operation identity does not create duplicate VAJRA-controlled side effects.

### G6 — Fencing

A stale worker cannot commit after lease/fencing invalidation.

### G7 — Loop

Repeated semantic activity without material progress triggers bounded recovery/escalation.

### G8 — Budgets

Budget exhaustion creates durable terminal/escalation state.

### G9 — Human boundary

`WAITING_HUMAN` cannot be escaped by model/worker output.

### G10 — Authority chain

Controller → Intent → Policy → Broker remains intact with no bypass.

---

# 41. Phase 8 — Context Engine

Build:

- repository indexer;
- deterministic retrieval;
- symbol/reference graph where useful;
- context ranking;
- provenance;
- freshness;
- bounded context reconstruction;
- history-aware context selection.

Embeddings/vector databases remain optional until benchmarked against simpler retrieval.

---

# 42. Phase 9 — Verification + Anti-Gaming

## 9A — Acceptance Criteria Compiler

Convert protected human criteria into machine-checkable verification plans where possible.

Uncompilable or ambiguous criteria MUST become explicit human-required conditions rather than guesses.

## 9B — Independent Verifier

Build a verifier the worker/model cannot control as proof authority.

## 9C — Test Integrity

Detect modification or weakening of protected verification inputs.

## 9D — Pristine Verification Environment

Isolate/recreate enough environment state that external contamination cannot invalidate verification.

## 9E — Evidence Integrity

Bind evidence to Run, Step/Attempt, workspace, repository revision, artifact, verifier version, executed check, output, and environment.

## 9F — Adversarial Verification

Test reward/specification gaming, hidden broken state, test tampering, verifier tampering, environment abuse, and stale-artifact verification.

---

# 43. Phase 10 — Real Autonomous Engineering Loop

Only after the Phase 7 safety gate and critical verification prerequisites pass.

```text
OBJECTIVE
   ↓
ORIENT
   ↓
RECONCILE
   ↓
CONTEXT
   ↓
PLAN
   ↓
INTENT
   ↓
POLICY
   ↓
EXECUTE
   ↓
OBSERVE
   ↓
VERIFY
   ↓
MEASURE PROGRESS
   ↓
RECONCILE
   ↓
DECIDE NEXT STEP
   ↓
repeat
```

Completion is an evidence-driven predicate, never a model decision.

---

# 44. Phase 11 — Chaos + Long-Run Reliability

Reliability testing begins as soon as the Controller exists and becomes systematic here.

Test dimensions:

- process kill;
- worker kill;
- model disappearance;
- network partition;
- lease expiry;
- stale result;
- state divergence;
- workspace corruption;
- retry storms;
- semantic loops;
- budget exhaustion;
- evidence growth;
- event growth;
- disk growth;
- memory growth;
- context staleness;
- verifier drift;
- resource leaks.

Progressive horizons:

```text
1 hour → 12 hours → 1 day → 3 days → 7 days → longer only when justified
```

Quantitative reliability envelopes MUST be derived from measured behavior.

---

# 45. Phase 12 — Model / Worker Routing

Introduce capability-aware routing after reliable single-run autonomy.

Requirements:

- stable ModelGateway contract;
- WorkerCapabilities;
- model identity/version recording;
- routing evidence;
- model-switch recovery;
- worker-switch recovery;
- budget-aware selection;
- failure-aware routing.

A second independently validated model/worker path SHOULD be proven before broad routing assumptions are made.

---

# 46. Phase 13 — Always-On Control Plane

Only after the autonomous core is reliable.

### 13A — Daemon

Durable local service for Run processing.

### 13B — Queue

Run scheduling and worker selection.

### 13C — Cancellation

Human pause/resume/cancel/abort controls.

### 13D — Scheduling

Durable scheduled Runs and periodic work.

### 13E — Telegram/API

External interfaces are control surfaces only.

```text
Human
  ↓
Telegram/API
  ↓
VAJRA control interface
  ↓
Durable Run
```

The external interface never owns canonical Run state.

---

# 47. Phase 14 — Engineering Memory

Build after history, truth, context, and verification are mature.

### 14A — Failure Memory

Store provenance-bound failure signatures and outcomes.

### 14B — Repository Memory

Track recurring architecture, conventions, decisions, and verification history with current-state validation.

### 14C — Context Memory

Retain useful context without losing provenance.

### 14D — Conflict Awareness

Current repository/verification truth always outranks historical memory.

---

# 48. Phase 15 — Production Hardening

Security hardening includes filesystem boundaries, symlinks, TOCTOU, credentials, Git hooks, submodules, package scripts, network, environment variables, sandbox configuration, worker authentication, result replay, prompt injection, and malicious repositories.

Resource controls include CPU, memory, disk, process count, network, output, model calls, and worker runtime.

Observability must expose enough durable evidence to explain the complete Run.

---

# 49. Phase 16 — Advanced Autonomy

Only after reliable single-run autonomy.

Potential capabilities:

- multi-step engineering objectives;
- multi-repository work;
- specialized workers;
- richer planning;
- richer repository reasoning;
- controlled concurrency.

Each capability requires its own authority, isolation, verification, and chaos gates.

---

# 50. Phase 17 — Controlled Self-Improvement

Allowed targets include heuristics, routing preferences, recovery tuning, retrieval ranking, and failure-memory organization.

The following MUST NOT be autonomously modified:

- canonical state authority;
- Policy authority;
- security boundaries;
- sandbox policy;
- verification authority;
- worker fencing;
- human override;
- evidence integrity;
- Execution Broker authority;
- audit/event integrity.

Changes to these require explicit human-controlled development and verification.

---

# 51. Phase 18+ — Research / Long Horizon

Possible future research:

- RLM / λ-RLM;
- semantic embeddings;
- advanced graph retrieval;
- long-context strategies;
- looped/recurrent model architectures;
- distributed worker pools;
- multi-agent collaboration;
- formal verification;
- advanced engineering memory;
- long-horizon multi-repository engineering.

No research feature becomes a foundation dependency merely because it appears promising.

---

# 52. Dependency Rules

1. Durable execution precedes autonomy.
2. Canonical truth and reconciliation precede autonomous continuation.
3. Minimal acceptance/completion predicates exist before autonomous completion.
4. Workspace ownership exists before controller decisions depend on workspace reality.
5. Idempotency and fencing are substrate invariants before meaningful concurrency.
6. Critical independent verification primitives exist before the autonomous loop can declare completion.
7. Context provenance and freshness exist before long-horizon reasoning.
8. Chaos testing begins as soon as the Controller exists.
9. Full long-run testing follows operational autonomous-loop validation.
10. Routing follows reliable single-run autonomy.
11. Always-on interfaces follow the autonomous core.
12. Memory follows mature history/context/truth systems.
13. Advanced autonomy follows reliable unattended engineering.
14. Self-improvement never controls the protected core.
15. Research remains optional until experimentally justified.

---

# 53. Milestones

## M1 — Durable Substrate

**Phase 6 — COMPLETE**

VAJRA can execute controlled engineering operations and preserve durable Run state through worker/process failure.

## M2 — Safe Autonomous Decision-Making

**Phases 7–9**

VAJRA can decide what to do next without allowing the model to become authority and without accepting unverified progress.

## M3 — Autonomous Engineering

**Phase 10**

```text
objective
→ orient
→ plan
→ code
→ test
→ debug
→ verify
→ recover
→ repeat
→ complete
```

## M4 — Reliable Unattended Engineering

**Phases 11–15**

Hours → days → weeks with controlled failure, divergence, resource, context, and verification behavior.

## M5 — Advanced Engineering Intelligence

**Phase 16+**

Multi-repo, multi-worker, specialized reasoning, engineering memory, controlled self-improvement, and long-horizon objectives.

---

# 54. Architecture Decision Matrix

| Proposal | Decision | Reason |
|---|---|---|
| Durable Run Controller | KEEP | Required missing authority layer |
| Reality reconciliation | KEEP | Required by truth laws |
| Progress ledger | KEEP | Required by evidence law |
| Completion predicate | KEEP | Prevents model-authorized completion |
| Operation identity | KEEP | Replay/stale-effect protection |
| Idempotency | KEEP | Recovery correctness |
| Fencing | KEEP + EXTEND | Existing worker mechanism must protect broader mutable effects |
| Worktree manager | MOVE EARLIER | Controller/reconciliation depend on workspace truth |
| Resource isolation | MODIFY | Minimal deterministic resources first |
| Context provenance | KEEP | Prevents context-authority confusion |
| Context freshness | KEEP | Prevents stale reasoning |
| Deterministic retrieval | KEEP | Strong foundation; benchmark alternatives |
| Full vector DB | RESEARCH | Not justified as foundation |
| Acceptance compiler | MOVE PREREQUISITE CONTRACT | Completion depends on machine-checkable criteria |
| Independent verifier | MOVE CRITICAL PRIMITIVES EARLIER | Model must not prove itself |
| Anti-gaming | KEEP | Required for reliable completion |
| Semantic loop detector | KEEP | Budgets alone are insufficient |
| Entropy monitor | RESEARCH | Definition/evidence not yet strong enough |
| ALDG | RESEARCH | Optimization, not safety foundation |
| RLM | RESEARCH | Context strategy, not runtime authority |
| λ-RLM | RESEARCH | Interesting bounded reasoning model |
| Looped Transformers | FUTURE | Model architecture, not runtime architecture |
| Engineering Memory | KEEP LATER | History-first remains correct |
| Differential skill execution | RESEARCH | Interesting but not core dependency |
| Cryptographic event chain | RESEARCH | Threat-model dependent |
| Oracle deployment | OPTIONAL | Not proven and not required under ₹0 constraint |
| Kaggle worker | KEEP AS OPTIONAL WORKER | Physical remote path validated |
| Telegram | LATER | Control surface only |
| Kubernetes | REJECT FOR NOW | No demonstrated need |
| Multi-agent swarm | LATER | Single-run autonomy first |
| Autonomous security changes | REJECT | Protected core boundary |
| Arbitrary Python authority | REJECT | Violates Laws 1 and 4 |
| Worker self-report as proof | REJECT | Violates Law 6 |
| Event log as physical truth | REJECT | Violates Laws 2, 11, 13 |

---

# 55. Phase 7 Design Freeze Checklist

Before Phase 7 implementation begins, the following MUST be specified and reviewed:

1. `ReconciliationReport` schema.
2. Authority mapping for every state source.
3. Divergence classes and deterministic dispositions.
4. Freshness semantics.
5. `ProgressRecord` schema.
6. `ProgressPredicate` semantics.
7. `CompletionPredicate` semantics.
8. `AcceptanceCriteria` schema and freeze rules.
9. `OperationIdentity` schema.
10. Idempotency-key derivation.
11. Idempotency replay semantics.
12. External-side-effect policy.
13. Lease/fencing semantics.
14. Workspace ownership/lifecycle.
15. Git operation serialization model.
16. Minimal resource-isolation model.
17. Controller input/output contract.
18. Legal transition table.
19. Human escalation entry/exit rules.
20. Hard-budget enforcement points.
21. Anti-loop fingerprint definition.
22. Evidence linkage rules.
23. Protected verification prerequisites.
24. Controller Safety Gate test plan.

No item may be silently delegated to model behavior.

---

# 56. Required Implementation Invariants

### I1 — Authority

No model output directly mutates canonical state or performs privileged execution.

### I2 — Transition legality

Every Run state transition is validated against the legal transition table.

### I3 — Freshness

Controller decisions depending on mutable external state use fresh reconciliation.

### I4 — Evidence

Progress/completion decisions reference valid evidence.

### I5 — Attempt isolation

An Attempt cannot overwrite canonical state belonging to another Attempt.

### I6 — Fencing

A stale worker cannot commit protected effects.

### I7 — Replay

Replay of a completed VAJRA-controlled operation does not duplicate its effect.

### I8 — Budget

No operation intentionally continues beyond a hard exhausted budget.

### I9 — Human boundary

`WAITING_HUMAN` cannot be exited through model/worker claims.

### I10 — Verification independence

The actor attempting to satisfy an objective cannot silently redefine its proof.

### I11 — Context provenance

Untrusted context cannot silently become trusted policy/instruction/evidence.

### I12 — Current truth

Current authoritative observations override historical claims when they conflict.

### I13 — Ambiguity

Unresolved authoritative conflict results in safe halt/recovery/human escalation.

### I14 — Workspace ownership

An unattended Run cannot mutate a workspace owned by another Run.

### I15 — Protected core

Self-improvement cannot alter authority/security/verification/fencing/human-control boundaries autonomously.

---

# 57. Testing Philosophy

Validation levels:

```text
Unit
  ↓
Contract
  ↓
Integration
  ↓
Failure injection
  ↓
Adversarial verification
  ↓
Physical infrastructure
  ↓
Chaos
  ↓
Long-run
```

A passing mock test is not equivalent to a physical boundary proof.

Security-sensitive claims prefer physical validation. Probabilistic/model claims require controlled benchmarks before architectural adoption.

---

# 58. Required Chaos Scenarios

At minimum:

```text
kill controller before transition
kill controller after durable transition
kill worker during execution
kill worker after side effect
expire lease before result
expire lease during result
network loss before dispatch
network loss after dispatch
network loss before result acceptance
filesystem divergence
Git revision divergence
workspace ownership conflict
stale context
stale verification
replayed operation
repeated identical failure
oscillating strategy
budget exhaustion
human pause during execution
human revoke during execution
verification harness modification
malicious repository instruction
sandbox failure
resource exhaustion
```

Every scenario requires a documented expected disposition.

---

# 59. Autonomous Core Completion Definition

The autonomous core is not complete merely because a model can modify code.

It requires:

```text
objective
  ↓
protected acceptance
  ↓
context
  ↓
model proposal
  ↓
policy
  ↓
broker
  ↓
sandbox/workspace
  ↓
artifact
  ↓
independent verification
  ↓
evidence
  ↓
progress predicate
  ↓
reconciliation
  ↓
controller decision
  ↓
repeat or safe termination
```

The Run must remain reconstructable after model, worker, process, network, or machine failure.

---

# 60. Zero-Cost Architecture Policy

The zero-cost constraint affects implementation choices but MUST NOT weaken safety or authority boundaries.

Prefer:

- local execution;
- free/open-source software;
- local durable storage;
- genuinely free compute tiers when available;
- ephemeral remote workers;
- model adapters instead of vendor lock-in;
- deterministic verification;
- bounded resource usage.

Never trade away canonical state, verification independence, sandbox boundaries, human authority, idempotency, fencing, evidence integrity, or durable recovery for cost.

Zero cost is a resource constraint, not a correctness compromise.

---

# 61. Final Architectural Statement

VAJRA is a durable evidence-driven engineering control system around disposable reasoning and execution components.

```text
                    HUMAN
                      │
                objective / policy
                      │
                      ▼
                 ENGINEERING RUN
                      │
                      ▼
                  CONTROLLER
                      │
            fresh reconciliation
                      │
                      ▼
                 CONTEXT ENGINE
                      │
                      ▼
                    MODEL
                      │
                  proposes
                      ▼
                    INTENT
                      │
                   POLICY
                      │
                      ▼
              EXECUTION BROKER
                      │
                RESOURCE/SANDBOX
                      │
                      ▼
                  ARTIFACT
                      │
                INDEPENDENT
                 VERIFICATION
                      │
                      ▼
                   EVIDENCE
                      │
              ┌───────┴────────┐
              ▼                ▼
           PROGRESS          TRUTH
           PREDICATE      RECONCILIATION
              │                │
              └───────┬────────┘
                      ▼
                  CONTROLLER
                      │
             next step / retry /
          human / abort / complete
```

The model supplies intelligence.

The worker supplies execution.

The verifier supplies evidence.

The workspace supplies observed engineering state.

The event history supplies auditability.

The durable runtime supplies survival.

**VAJRA owns the decision, authority, and canonical Run state.**

---

# 62. Current Position

```text
PHASE 6 — DURABLE SUBSTRATE
████████████████████████████  COMPLETE

PHASE 7 — AUTONOMOUS CONTROL FOUNDATION
                            ← CURRENT

PHASE 8 — CONTEXT ENGINE
PHASE 9 — VERIFICATION + ANTI-GAMING
PHASE 10 — AUTONOMOUS ENGINEERING LOOP
PHASE 11 — CHAOS / LONG-RUN
PHASE 12 — ROUTING
PHASE 13 — ALWAYS-ON
PHASE 14 — MEMORY
PHASE 15 — HARDENING
PHASE 16 — ADVANCED AUTONOMY
PHASE 17 — CONTROLLED SELF-IMPROVEMENT
PHASE 18+ — RESEARCH
```

The next engineering action is to convert this specification into concrete Phase 7 contracts, validate them against the current implementation, and then implement 7A behind the Controller Safety Gate.

---

# 63. Document Authority

This document is the forward-looking architecture/specification for post-Phase-6 VAJRA development.

The historical v0 specification remains authoritative for already-established substrate contracts unless this document explicitly extends or supersedes them.

When implementation, documentation, research, and assumptions conflict, use this evaluation order:

```text
Architectural Laws
      ↓
Current approved specification
      ↓
Physical test evidence
      ↓
Current implementation
      ↓
Research proposals
      ↓
Unverified assumptions
```

No research review, model output, or generated plan may silently override the architectural laws.

---

**End of VAJRA v1 Architecture & Roadmap Specification**