# VAJRA — Current State

**Project:** VAJRA  
**Version:** v0.1.0 baseline + post-v0 operationalization  
**Phase:** Phase 11 — Long-Run Durability + Chaos complete  
**Implementation status:** Phase 11 complete; Phase 12 not started  
**Frozen baseline:** `v0.1.0` / `fb3cca5`  
**Operating-cost constraint:** ₹0.00

---

## 1. Project Definition

VAJRA is a durable autonomous engineering runtime that accepts an engineering objective and is designed to produce a verified engineering artifact while preserving canonical state across worker, model, process, network, and machine failure.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram bot, model-hosting platform, or collection of shell scripts.

The fundamental guarantee is:

> A worker, model, process, network connection, or machine may disappear without destroying the Engineering Run.

Canonical state belongs to VAJRA, not to models or workers.

---

## 2. Canonical Specifications

Primary architecture/specification sources:

- `docs/VAJRA_v0_Technical_Specification.txt`
- `docs/VAJRA_v1_Architecture_and_Roadmap_Specification.md`
- `docs/PHASE_7_DESIGN_FREEZE.md`

The v0 specification remains architectural authority. Historical status text inside the original specification is historical; this file records current repository status.

---

## 3. Architectural Laws

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

The operating boundary is:

```text
OBJECTIVE
   ↓
CONTEXT
   ↓
MODEL / REASONING
   ↓
INTENT
   ↓
POLICY
   ↓
EXECUTION BROKER
   ↓
SANDBOX / WORKSPACE
   ↓
ARTIFACT
   ↓
INDEPENDENT VERIFICATION
   ↓
EVIDENCE
   ↓
PROGRESS / RECOVERY / HUMAN / COMPLETION
```

The model is inside VAJRA, never above VAJRA.

---

## 4. Phase Status

| Phase | Status | Evidence |
|---|---|---|
| Phase 6 — Core implementation | COMPLETE / FROZEN | `fb3cca5`, tag `v0.1.0` |
| Phase 7 — Safety foundation + autonomous control | COMPLETE / Gate F PASSED | Gate F integration and real-path tests |
| Phase 8 — Context + workspace | COMPLETE | context/workspace suite and full validation |
| Phase 9 — Verification + evidence integrity | COMPLETE / Gate PASSED | verification, anti-gaming, integrity and environment tests |
| Phase 10 — Autonomous engineering loop | COMPLETE / Gate PASSED | end-to-end loop, safety boundaries, portable CI |
| Phase 11 — Long-run durability + chaos | COMPLETE / Gate PASSED | kill harness, divergence, retry storm, lease chaos, soak runner and portable CI |
| Phase 12 — Model + worker routing | NOT STARTED | blocked by roadmap ordering until Phase 11 is complete |

---

## 5. Phase 6 Frozen Baseline

Phase 6 established the runtime foundation and was frozen at:

- commit: `fb3cca5`
- tag: `v0.1.0`
- operating cost: ₹0.00
- baseline working tree: clean

The baseline established the durable distinction:

```text
Run      = durable
Step     = durable
Attempt  = disposable
Worker   = disposable
Model    = disposable
```

The baseline remains immutable. Later work proceeds on `main`.

---

## 6. Physical Gates

### Gate A — Durable Recovery

PASS. Run/process recovery and idempotency behavior were physically validated.

### Gate B — Local model

Evaluated as an infrastructure capability rather than a VAJRA authority dependency.

### Gate C — Remote worker

PASS WITH INFRASTRUCTURE LIMITATION. The physical path was exercised through HTTP transport to a remote worker using Qwen 2.5 Coder 32B. Oracle-hosted deployment was not claimed because the zero-cost/no-credit-card constraint prevented that infrastructure.

### Gate D — Sandbox

PASS. gVisor through Docker/runsc was physically validated and selected as the v0 sandbox backend. Physical Firecracker proof was not claimed because suitable guest assets and complete guest isolation proof were unavailable.

### Gate E — ASTRA extraction

PASS WITH LIMITATIONS. Only proven useful behaviors were carried into VAJRA; ASTRA is not a VAJRA runtime dependency.

### Gate F — Autonomous control safety

PASS. Phase 7 validated frozen acceptance, fresh reconciliation, ownership, idempotency, controller authority, hard budgets, no-progress behavior, repeated-failure protection and chaos scenarios.

---

## 7. Phase 8 — Context + Workspace

Phase 8 established:

- Git worktree lifecycle primitives
- deterministic context construction/retrieval
- trust tagging
- context freshness
- workspace/reality boundaries
- deterministic digests

Validation reached the full repository suite with clean compile and diff checks.

---

## 8. Phase 9 — Independent Verification

Phase 9 established:

- acceptance criteria compiler
- independent verifier
- test-integrity / anti-gaming controls
- pristine verification environment
- immutable/content-addressed verification evidence
- adversarial verification coverage

Worker/model output is not treated as proof.

---

## 9. Phase 10 — Autonomous Engineering Loop

Phase 10 wires the earlier primitives into the first bounded objective-to-evidence controller:

```text
OBJECTIVE
   ↓
ORIENT
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
DECIDE NEXT STEP
   ↓
repeat / recover / human / complete
```

The loop enforces:

- fresh context before reasoning
- context-bound structured plans
- proposal-only reasoning
- durable Run/Step/Attempt identities
- policy authorization before execution
- broker-only execution
- lease/result fencing
- independent verification
- durable evidence recording
- deterministic progress measurement
- bounded no-progress/retry behavior
- recovery-driven replanning
- explicit human escalation
- hard cycle/resource termination
- evidence-bound promotion/completion

---

## 10. Phase 11 — Long-Run Durability + Chaos

**Status: COMPLETE / CLOSED**

Phase 11 follows the roadmap order: chaos and long-run reliability are validated before model/worker routing.

### 11A — Kill testing

`ChaosPlan` and `FaultInjector` provide seeded, reproducible fault schedules covering:

- controller
- worker
- model
- process
- network
- sandbox
- machine simulation

`KillHarness` adds a real disposable process boundary. Each modeled failure domain durably records a STARTED execution, receives `SIGKILL`, and is then reopened by a fresh runtime instance to verify recovery discovery.

The harness validates the shared VAJRA durability boundary. It does not falsely claim that every external infrastructure domain was physically destroyed on the host.

### 11B — State divergence

Reality changes are detected through deterministic digests while the existing Phase 7 `RealityObserver` remains the canonical reconciliation boundary.

### 11C — Retry storms

`RetryStormGuard` bounds repeated identical failures per run/step/failure signature and produces a termination decision at the configured threshold.

### 11D — Lease chaos

The real worker result acceptance path verifies that worker A cannot overwrite state after worker B has taken the lease/fencing position.

### 11E — Long-duration runs

The roadmap profiles are explicitly represented:

- 1 hour
- 12 hours
- 3 days
- 7 days
- 30 days

`SoakRunner` now provides real elapsed-time execution with monotonic timing, configurable sampling, Linux RSS measurement, workspace disk measurement, and runtime counters for all roadmap signals:

- memory growth
- disk growth
- event growth
- context growth
- worker leaks
- stale leases
- retry counts
- verification failures
- provider failures
- clock anomalies

Accelerated tests validate runner mechanics only. They are never represented as equivalent to real 1h/12h/3d/7d/30d elapsed-time evidence.

### Phase 11 validation

The dedicated suite covers the kill harness and soak runner in addition to the earlier Phase 11 safety tests. Hosted CI runs the dedicated suite, portable full suite, compile validation and diff validation. gVisor integration remains environment-specific and is not silently converted into hosted-CI proof.

---

## 11. Current Limitations

The following are explicit infrastructure/evidence boundaries, not hidden requirements:

1. Oracle-hosted infrastructure remains unproven because the project is constrained to ₹0.00/no paid infrastructure.
2. Physical gVisor proof is environment-specific and is not reproduced by hosted CI.
3. Real multi-day soak campaigns require an operator to leave the runner executing for the selected elapsed duration. Accelerated CI cannot prove elapsed-time behavior.
4. The local durable runtime remains a development/reference implementation, not the final distributed production durability backend.
5. Phase 12 model/worker routing has not started.

No paid service is required to continue development.

---

## 12. Explicitly Deferred

Until a later roadmap phase or explicit design decision:

- distributed worker pool
- multiple concurrent Runs
- Kubernetes
- automatic model fine-tuning
- complex multi-agent collaboration
- vector database
- Telegram as autonomous control plane
- Needle as mandatory v0 dependency
- ASTRA legacy core as a runtime dependency
- premature v1 infrastructure

---

## 13. Next Phase Boundary

Phase 12 may now begin because Phase 11 is complete.

The next roadmap area is **MODEL + WORKER ROUTING**, not a replacement of the existing authority model. Routing must preserve the invariant:

```text
Model proposes
→ VAJRA decides
→ Policy authorizes
→ Broker executes
→ Verifier proves
→ Evidence records
→ Controller continues safely
```

No routing layer may become an authority bypass.

---

## 14. Frozen Baseline Rule

`v0.1.0` at commit `fb3cca5` is immutable.

Do not delete, rewrite, or retag `v0.1.0`.

All post-v0 work proceeds from `main` while preserving the canonical specifications and architectural laws.
