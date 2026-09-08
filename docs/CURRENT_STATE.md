# VAJRA — Current State

**Project:** VAJRA  
**Version:** v0  
**Phase:** Phase 5 — Architecture / Gate Closure  
**Implementation status:** Not yet implemented  
**Operating-cost constraint:** ₹0.00

---

## 1. Project Definition

VAJRA is a durable autonomous engineering runtime that accepts an engineering
objective and attempts to produce a verified engineering artifact.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram
bot, model-hosting platform, or collection of shell scripts.

The fundamental guarantee is:

> A worker, model, process, network connection, or machine may disappear
> without destroying the Engineering Run.

Canonical state belongs to VAJRA, not to models or workers.

---

## 2. Canonical Specification

The canonical v0 technical specification is:

`docs/VAJRA_v0_Technical_Specification.txt`

The original PDF is:

`VAJRA v0 Technical Specification.pdf`

The specification defines the architectural laws, system planes,
Engineering Run model, worker protocol, policy boundary, execution boundary,
sandbox abstraction, verification semantics, recovery model, budgets,
security boundary, topology, v0 scope, and Phase 5 exit criteria.

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

    MODEL
      |
      v
    INTENT
      |
      v
    POLICY
      |
      v
    EXECUTION
      |
      v
    ARTIFACT
      |
      v
    EVIDENCE
      |
      v
    ENGINEERING PROGRESS

The model is inside VAJRA, never above VAJRA.

---

## 4. Phase 5 Gate Status

| Gate | Result | Current decision |
|---|---|---|
| A — Durable Recovery | PASS | Accepted |
| B — Needle Benchmark | REJECT | Needle dropped as mandatory v0 dependency |
| C — Kaggle Worker Lifecycle | BLOCKED / INCOMPLETE | Oracle lifecycle still required |
| D — Sandbox Isolation | REWORK | Current gVisor resource boundary not accepted |
| E — ASTRA Safety Extraction | PASS WITH LIMITATIONS | Proven behavior may be adapted |

Phase 5 is therefore **not closed**.

Architecture is **not frozen**.

---

## 5. Gate A — Durable Recovery

Status: **PASS**

The durable recovery prototype demonstrated:

- Run creation
- Step execution
- checkpoint persistence
- interruption
- process/runtime restart
- recovery
- preservation of durable state
- coherent recovery state

The Engineering Run survives worker/process/runtime disappearance.

---

## 6. Gate B — Needle

Status: **REJECT / DROP NEEDLE**

Needle was benchmarked on the actual laptop.

The measured value was insufficient to justify retaining Needle as a
required local specialist in v0.

Decision:

- Do not retain Needle as a mandatory v0 dependency.
- VAJRA remains model-agnostic.
- Local llama.cpp/Ollama and remote workers remain available through the
  Model Gateway abstraction.

Needle may remain a historical/reference concept but is not an architectural
requirement.

---

## 7. Gate C — Oracle → Kaggle Worker Lifecycle

Status: **BLOCKED / INCOMPLETE**

The following portions were exercised successfully:

- Kaggle worker environment
- Ollama runtime
- model availability
- inference
- worker protocol
- remote connectivity
- coding-task behavior

The complete canonical Oracle-controlled lifecycle was not proven because
the Oracle environment/account was unavailable.

Still unproven:

- Oracle canonical Run state
- Oracle → Kaggle dispatch
- complete Attempt correlation
- worker-loss recovery under Oracle control
- stale-worker protection
- Oracle-controlled retry

A prior protocol test also showed that a disposable worker generated its own
request identifier instead of preserving the laptop/control request
identifier.

Gate C must not be marked PASS until the complete physical lifecycle is
tested.

---

## 8. Gate D — Sandbox Isolation

Status: **REWORK**

gVisor successfully demonstrated:

- host filesystem isolation
- Docker socket isolation
- path traversal blocking
- symlink escape blocking
- process namespace isolation
- unauthorized localhost access blocking
- external networking denied with `--network=none`
- common credential locations not visible

However, the resource boundary was not proven.

Host environment:

- `CgroupVersion=2`
- `CgroupDriver=systemd`

Observed gVisor environment:

- cgroup v1 = true
- cgroup v2 = false
- systemd = false
- systemdUser = false

The controlled resource test did not demonstrate the required Docker-provided
CPU/memory/PID limits inside gVisor.

A resource-limit startup attempt failed with:

`cannot create sandbox: cannot read client sync file: waiting for sandbox to start: EOF`

The earlier host-impacting resource experiment is not accepted as evidence
because the host rebooted and the experiment did not produce a controlled,
attributable acceptance result.

Firecracker was validated at host/KVM/API level:

- Firecracker v1.16.1
- `/dev/kvm` available
- KVM hardware virtualization available
- API process started

However, a suitable guest kernel/rootfs pair was not available, so guest
boot and isolation were not proven.

Decision:

- Do not freeze the current gVisor configuration as the production sandbox.
- Do not claim Firecracker as validated.
- Keep the SandboxBackend abstraction.
- Rework Gate D before architecture freeze.

No further speculative sandbox stress testing is required on the current
environment.

---

## 9. Gate E — ASTRA Safety Extraction

Status: **PASS WITH LIMITATIONS**

ASTRA v1.10.0-rc1 was treated as a reference implementation rather than a
dependency.

Targeted tracked tests:

`81/81 passed`

Proven safety areas included:

- detection hardening
- patch generation and safety
- command policy
- checkpoint handling
- mutation/apply safety
- rollback/recovery
- release hardening
- validation/project safety

Decision:

- Adapt only proven behavior.
- Do not import the ASTRA legacy core wholesale.
- No ASTRA architectural dependency is permitted in VAJRA.

---

## 10. Accepted Architectural Decisions

The following are accepted:

- durable Engineering Run as the primary durable object
- durable Steps
- disposable Attempts
- append-oriented event history
- model-agnostic Model Gateway
- deterministic Policy Engine
- Execution Broker as the only execution authority
- Git worktree as the logical workspace mechanism
- abstract SandboxBackend
- independent Verification Engine
- explicit Failure and Recovery model
- explicit Run budgets
- human escalation through durable state
- one active Run for v0
- one active worker for v0
- one repository for v0
- history-first memory
- ASTRA as reference only

---

## 11. Explicitly Rejected

The following are not v0 dependencies:

- Needle as mandatory local specialist
- ASTRA legacy core
- Telegram as autonomous control plane
- vector database
- distributed worker pool
- multiple concurrent Runs
- Kubernetes
- automatic model fine-tuning
- complex multi-agent collaboration

The current gVisor resource-control configuration is also not accepted as a
frozen production sandbox.

---

## 12. Remaining Phase 5 Work

Only the following blockers remain material:

### Gate C

Prove the complete Oracle-controlled worker lifecycle:

    Oracle
      |
      v
    dispatch
      |
      v
    Kaggle worker
      |
      v
    inference / coding
      |
      v
    structured result
      |
      v
    Attempt correlation
      |
      v
    worker disappearance
      |
      v
    durable recovery / retry

The test must also prove stale-worker protection.

### Gate D

Resolve the sandbox backend/resource-boundary issue and produce acceptance
evidence for the selected production execution boundary.

---

## 13. Phase 6 Boundary

Phase 6 must not begin until the required Phase 5 gates are closed.

When Phase 5 closes, implementation proceeds in this order:

    VAJRA repository
        |
        v
    schemas
        |
        v
    durable runtime
        |
        v
    Run lifecycle
        |
        v
    worker protocol
        |
        v
    policy
        |
        v
    execution
        |
        v
    verification
        |
        v
    recovery

No feature should be implemented merely because it is interesting.

Every implementation must trace back to the v0 specification.

---

## 14. Current Verdict

**PHASE 5 — REWORK REQUIRED**

The architecture is sufficiently defined to proceed toward implementation
planning, but it is not yet frozen.

Gate C and Gate D remain the only material gate blockers.

No completed gate should be rerun merely for repetition.

