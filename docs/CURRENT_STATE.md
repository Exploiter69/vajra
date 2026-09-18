# VAJRA — Current State

**Project:** VAJRA  
**Version:** v0.1.0 baseline + post-v0 operationalization  
**Phase:** Phase 17 — Controlled Self-Improvement  
**Implementation status:** Phase 17 COMPLETE / local gate PASSED  
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
| Phase 12 — Model + worker routing | COMPLETE / Gate PASSED | gateway, capability routing, switching/recovery, routing evidence, portable CI |
| Phase 13 — Always-on control plane | COMPLETE / CLOSED | daemon, durable queue, human controls, scheduling, API |
| Phase 14 — Engineering Memory | COMPLETE / CLOSED | failure, repository, context memory and conflict awareness |
| Phase 15 — Production Hardening | COMPLETE / CLOSED | security, resource controls, observability; final local gate passed |
| Phase 16 — Advanced Autonomy | COMPLETE / CLOSED | multi-step, multi-repository, specialized workers, durable long-horizon bounds; 9 dedicated tests and 661 portable-suite tests passed |
| Phase 17 — Controlled Self-Improvement | COMPLETE / LOCAL GATE PASSED | bounded improvement proposals, protected authority surfaces, isolated verification/security gates, explicit human promotion, durable journal |

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

The loop enforces fresh context, proposal-only reasoning, policy authorization, broker-only execution, lease/result fencing, independent verification, evidence recording, deterministic progress, bounded recovery, human escalation, and hard termination.

---

## 10. Phase 11 — Long-Run Durability + Chaos

**Status: COMPLETE / CLOSED**

Phase 11 established deterministic chaos schedules, real disposable-process kill/recovery validation, state-divergence detection, bounded retry-storm handling, lease fencing coverage, and a real elapsed-time soak runner with explicit 1h / 12h / 3d / 7d / 30d profiles.

Accelerated tests validate runner mechanics only; they do not claim real elapsed-time evidence.

---

## 11. Phase 12 — Model + Worker Routing

**Status: COMPLETE / CLOSED**

Phase 12 implements every roadmap subsection without changing the authority model.

### 12A — Model abstraction

`src/vajra/routing/contracts.py` and `gateway.py` provide:

- stable `ModelGateway` contract;
- `ModelRequest` with run/step/attempt identity, task, context, tools, output schema, budget, deadline, model and strategy;
- `ModelResult` with status, structured output, raw output reference, usage, model identity, errors and routing evidence;
- versioned `ModelIdentity` (provider/model/version/adapter);
- `ModelUsage` accounting;
- registry-based, dependency-free adapters.

### 12B — Complexity routing

`CapabilityRouter` supports simple, mechanical, complex and difficult work classification and deterministic worker selection based on task support, required capabilities, model preference, availability and budget. Selection evidence records the complete candidate set and chosen worker/model.

### 12C — Model switching

`RoutingRecovery` implements bounded recovery through same-model retry, strategy change, different model, different worker, and human escalation when alternatives are exhausted.

### 12D — Capability-based workers

`WorkerCapabilities` records accelerator, VRAM, system RAM, model, model version, context limit, supported tasks, sandbox type and network policy. No GPU/vendor name is hard-coded as a routing authority.

### Authority preservation

Routing only selects resources. It does not authorize operations, mutate canonical Run state, replace leases, execute commands, or establish verification evidence. Any routed attempt remains subject to the existing Policy, Execution Broker, lease/fencing, sandbox/workspace, and independent Verification boundaries.

### Phase 12 validation

`tests/routing/test_phase12_routing.py` covers model identity/version/usage, gateway failure behavior, complexity classification, capability fit, deterministic selection, budget enforcement, fail-closed routing, routing evidence, model/worker switching, bounded retries, strategy changes and human escalation. `.github/workflows/phase12-validation.yml` runs the routing suite, portable full suite, compilation and diff checks.

### Phase 13 — Always-On Control Plane

**Status: COMPLETE / CLOSED**

Phase 13 implements the canonical roadmap's 13A–13E scope:

- 13A daemon with clean start/stop and restart-aware dispatch;
- 13B append-only fsync-backed durable queue with claim recovery and executor-failure requeue;
- 13C pause/resume/cancel/abort/retry/approve/reject human controls through RunManager and TransitionAuthority;
- 13D persisted one-shot and periodic schedules plus registered background-job handlers;
- 13E localhost-by-default HTTP/JSON API as a replaceable control surface.

The control plane does not own canonical Run state, execute model/worker work itself, or make Telegram/external cron a source of truth. PAUSED stops the current autonomous-loop invocation until an explicit human resume. CANCEL is resumable; ABORT is terminal.

### Explicit boundaries

- Oracle remains optional/unproven under the ₹0.00 constraint.
- Kaggle remains an ephemeral worker, never canonical state.
- No paid inference or infrastructure was introduced.
- Phase 13 now provides the always-on control plane.
- Phase 14 Engineering Memory and Phase 15 Production Hardening are complete and closed.

---

## 12. Phase 14 — Engineering Memory

**Status: COMPLETE / CLOSED**

Phase 14 implements the canonical roadmap's 14A–14D scope without making historical memory authoritative.

### 14A — Failure Memory

Provenance-bound failure signatures and outcomes are stored with Run/Step/Attempt identity, repository state, and mandatory source references.

### 14B — Repository Memory

Architecture, conventions, structured decisions, and verification history are retained with repository revision/digest. Current-state validation marks historical repository memory stale when authoritative repository state changes.

### 14C — Context Memory

Bounded context items are retained with repository revision, context digest, item provenance, and source references. Current revision/digest changes invalidate historical context rather than silently reusing it.

### 14D — Conflict Awareness

Current repository and verification truth outrank memory. Explicit MemoryConflict records use CURRENT_TRUTH_WINS. Corrections are append-only via supersedes; superseded history remains auditable but is hidden from normal queries.

### Phase 14 validation

The final Phase 14 local gate passed: 8 dedicated memory tests, 643 portable-suite tests with 4 gVisor tests deselected, compilation, and git diff checks. Memory tests cover persistence/reload, provenance enforcement, repository/context staleness, deterministic querying, supersession, identity separation, and journal tamper detection. The GitHub Actions workflow remains configured for equivalent validation; its final push-triggered hosted result was not independently observable through the available connector.

No vector database, embeddings, autonomous memory rewriting, model-controlled memory authority, or paid infrastructure was introduced.

---

## 13. Phase 16 — Advanced Autonomy

**Status: COMPLETE / CLOSED**

Phase 16 implements 16A–16D from the canonical roadmap. Multi-step engineering is represented as a dependency-validated stage graph; multi-repository work requires explicit repository authority; specialized workers are deterministic singular role resources rather than a default swarm; and long-horizon objectives use durable stage checkpoints plus hard bounds and resume behavior.

The Phase 16 layer does not authorize execution, mutate canonical Run state directly, replace independent verification, or grant models authority. It composes the existing Policy → Broker → Sandbox/Workspace → Verification boundaries.

## 14. Current Limitations

1. Oracle-hosted infrastructure remains unproven because the project is constrained to ₹0.00/no paid infrastructure.
2. Physical gVisor proof is environment-specific and is not reproduced by hosted CI.
3. Real multi-day soak campaigns require an operator to leave the runner executing for the selected elapsed duration. Accelerated CI cannot prove elapsed-time behavior.
4. The local durable runtime remains a development/reference implementation, not the final distributed production durability backend.

These are explicit infrastructure/evidence boundaries, not hidden Phase 12 requirements.

---

## 15. Explicitly Deferred

Until a later roadmap phase or explicit design decision:

- distributed worker pool beyond the Phase 12 capability abstraction
- multiple concurrent Runs
- Kubernetes
- automatic model fine-tuning
- complex multi-agent collaboration
- vector database
- Telegram as autonomous control plane
- Needle as mandatory v0 dependency
- ASTRA legacy core as a runtime dependency
- premature research/future infrastructure

---

## 16. Next Phase Boundary

Phases 15 and 16 are complete and closed. Phase 17 is also complete after its final local gate. The next roadmap boundary is **PHASE 18+ — RESEARCH / LONG HORIZON**.

The routing layer remains subordinate to the existing authority chain:

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

## 16. Phase 17 — Controlled Self-Improvement

**Status: IMPLEMENTED / GATE PENDING**

Phase 17 implements the roadmap's complete self-improvement scope. Eligible improvements are limited to routing heuristics, recovery heuristics, context ranking, failure classification, memory strategies, scheduling heuristics, and worker selection.

Protected forever: Policy authority, security boundary, sandbox primitives, verification authority, worker fencing, canonical state, human override, audit/event integrity, Execution Broker boundary, autonomy/control-plane authority, and the self-improvement guard itself.

The lifecycle is proposal → isolated branch → tests → independent verification → security verification → human approval → promotion. The model may propose a change but cannot manufacture approval, promote it, alter protected authority, or restart itself.

## 17. Frozen Baseline Rule

`v0.1.0` at commit `fb3cca5` is immutable.

Do not delete, rewrite, or retag `v0.1.0`.

All post-v0 work proceeds from `main` while preserving the canonical specifications and architectural laws.
