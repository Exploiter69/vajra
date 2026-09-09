# VAJRA — Current State

**Project:** VAJRA  
**Version:** v0.1.0 baseline  
**Phase:** Phase 6 — Implementation complete  
**Implementation status:** Phase 6 complete; post-v0 operationalization pending  
**Baseline commit:** `fb3cca5`  
**Baseline tag:** `v0.1.0`  
**Test suite at freeze:** 419 passed  
**Operating-cost constraint:** ₹0.00

---

## 1. Project Definition

VAJRA is a durable autonomous engineering runtime that accepts an engineering objective and is designed to produce a verified engineering artifact while preserving canonical state across worker, model, process, network, and machine failure.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram bot, model-hosting platform, or collection of shell scripts.

The fundamental guarantee is:

> A worker, model, process, network connection, or machine may disappear without destroying the Engineering Run.

Canonical state belongs to VAJRA, not to models or workers.

---

## 2. Canonical Specification

The canonical v0 technical specification is:

`docs/VAJRA_v0_Technical_Specification.txt`

The original PDF is:

`VAJRA v0 Technical Specification.pdf`

The specification remains the architectural authority. It defines the architectural laws, system planes, Engineering Run model, worker protocol, policy boundary, execution boundary, sandbox abstraction, verification semantics, recovery model, budgets, security boundary, topology, v0 scope, and implementation sequence.

The specification was written before implementation and contains historical Phase 5 status text. That historical text is not the current implementation status; this file records the actual repository state.

---

## 3. Architectural Laws

The following remain normative:

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

Core boundary:

    OBJECTIVE
      |
      v
    CONTEXT
      |
      v
    MODEL / REASONING
      |
      v
    INTENT
      |
      v
    POLICY
      |
      v
    EXECUTION BROKER
      |
      v
    SANDBOX / WORKSPACE
      |
      v
    ARTIFACT
      |
      v
    VERIFICATION
      |
      v
    EVIDENCE
      |
      v
    NEXT STEP / RECOVERY / COMPLETION

The model is inside VAJRA, never above VAJRA.

---

## 4. Phase 6 Final Status

Phase 6 implementation is complete and the v0.1.0 baseline is frozen.

Final integration gate:

- commit: `fb3cca5`
- working tree: clean
- `git diff --check`: clean
- full automated suite: `419 passed`
- tag: `v0.1.0`

The frozen baseline contains the implemented runtime foundation and safety boundaries. It does not yet constitute the complete autonomous engineering loop.

---

## 5. Gate Status

| Gate | Property | Result | Current decision |
|---|---|---|---|
| A | Durable Recovery | PASS | Accepted |
| B | Needle Benchmark | REJECT | Needle dropped as mandatory v0 dependency |
| C | Oracle → Kaggle Worker Lifecycle | PASS WITH INFRASTRUCTURE LIMITATION | Accepted without claiming Oracle-hosted deployment |
| D | Sandbox Isolation | PASS | gVisor selected as v0 sandbox backend |
| E | ASTRA Safety Extraction | PASS WITH LIMITATIONS | Proven behavior may be adapted; ASTRA is not a dependency |

### Gate C

Deterministic lifecycle evidence and the physical worker path established:

- canonical Run state remains under VAJRA control
- Worker Jobs correlate to the correct Step/Attempt
- lease/fencing protects result acceptance
- worker disappearance transitions into recovery
- replacement worker selection is supported
- Oracle-controlled retry creates a new Attempt with new lease/fencing
- stale workers cannot mutate canonical Run state
- Laptop → Cloudflare tunnel → Kaggle worker → Qwen 2.5 Coder 32B → WorkerResult was physically exercised

An Oracle VM was not available. Therefore an Oracle-hosted deployment itself is not claimed as physically proven.

### Gate D

gVisor through Docker/runsc was selected as the v0 sandbox backend. Validation covered filesystem/path traversal, symlink escape, process isolation, unauthorized network access, credential-location isolation, resource limits, and authorized execution. Firecracker was not selected because a suitable guest kernel/rootfs and complete guest isolation proof were unavailable in the test environment.

The SandboxBackend abstraction remains mandatory.

---

## 6. Implemented v0.1.0 Capabilities

### Domain and lifecycle

- Core domain contracts
- Engineering Run lifecycle
- durable Steps
- disposable Attempts
- checkpoints
- final dispositions
- bounded state transitions

### Durable runtime

- DurableRuntime abstraction
- restart-capable append-only reference runtime
- replay
- durable timers
- retry/recovery semantics
- execution lifecycle persistence

The local durable runtime is a development/reference implementation, not the final distributed production runtime.

### Worker protocol

- WorkerJob / WorkerResult contracts
- worker dispatch boundary
- lease management
- fencing
- canonical result acceptance
- worker disappearance detection
- Oracle-controlled retry
- worker-change recovery
- correlation identity preservation

### Policy and execution

- deterministic Policy Engine
- explicit ALLOW / DENY / MODIFY / HUMAN_REQUIRED decisions
- Execution Broker as execution authority
- bounded workspace file operations
- controlled process execution
- read-only Git inspection backend
- sandboxed execution boundary

### Verification and evidence

- independent command verification
- structured verification results
- acceptance evaluation
- content-addressed verification evidence

### Failure and recovery

- failure classification
- recovery policy
- recovery coordination
- retry / strategy / model / worker / checkpoint / human / abort actions
- no-progress detection
- budgets
- checkpoint persistence
- reconciliation
- human escalation

### CLI

The v0 CLI provides human control for Run creation, listing, status, events, transitions, abort, and snapshots. The CLI control surface is implemented; persistent production CLI storage still depends on the production canonical state backend.

### Sandbox and physical infrastructure

- RestrictedLocal reference sandbox
- gVisor Docker/runsc backend
- resource-limit translation
- Gate D security harness
- Kaggle worker integration path
- HTTP worker transport

---

## 7. Known v0.1.0 Limitations

The frozen baseline is intentionally a runtime foundation rather than a finished autonomous engineering product.

The following major operational layers are not yet fully wired into one durable end-to-end loop:

1. ContextBundle contract and deterministic context construction
2. Model Gateway / Model Adapter
3. model reasoning → structured engineering intents
4. operational Git worktree lifecycle
5. durable Run controller/orchestration of the full engineering loop
6. acceptance-criteria → executable verification conditions
7. persistent production state/event backend
8. production deployment of the always-on control plane

These are the primary post-v0 implementation targets.

---

## 8. Next Engineering Direction — Post-v0 Operationalization

Do not create an invented "Phase 7". The v0 specification defines the Phase 6 implementation sequence; the work after the frozen v0.1.0 baseline is post-v0 operationalization.

The target autonomous loop is:

    Engineering Objective
          |
          v
    Context Builder
          |
          v
    Model Gateway / Reasoning
          |
          v
    Structured Intent(s)
          |
          v
    Policy Engine
          |
          v
    Execution Broker
          |
          v
    Sandbox / Workspace
          |
          v
    Artifact / Change
          |
          v
    Independent Verification
          |
          v
    Evidence
          |
          v
    Run Controller
          |
          +------> next reasoning cycle
          |
          +------> recovery
          |
          +------> human escalation
          |
          +------> completion

The implementation must preserve all ten architectural laws while making this loop durable, bounded, evidence-driven, and recoverable.

---

## 9. Research Boundary Before Further Implementation

The v0.1.0 baseline is frozen while the autonomous-loop design is reviewed.

Independent research should focus on:

- durable autonomous engineering loops
- context engineering and minimal task-specific ContextBundles
- model selection and routing under the ₹0.00 constraint
- bounded autonomy and termination
- prevention of repeated patches, oscillation, retry storms, context drift, and false completion
- end-to-end evidence and verification
- future v1 capabilities without prematurely importing them into v0

Research must be evaluated against the VAJRA specification, current implementation, and architectural laws before code is changed.

---

## 10. Explicitly Rejected / Deferred

The following remain outside the frozen v0 baseline unless explicitly justified by the specification or a later design decision:

- Needle as mandatory local specialist
- ASTRA legacy core
- Telegram as autonomous control plane
- vector database
- distributed worker pool
- multiple concurrent Runs
- Kubernetes
- automatic model fine-tuning
- complex multi-agent collaboration
- premature v1 infrastructure

---

## 11. Frozen Baseline Rule

`v0.1.0` at commit `fb3cca5` is the immutable Phase 6 completion baseline.

Do not delete, rewrite, or retag `v0.1.0`.

Future work proceeds from `main` as post-v0 operationalization while preserving the v0 specification and architectural laws.
