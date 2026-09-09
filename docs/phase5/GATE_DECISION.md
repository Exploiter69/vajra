# VAJRA v0 — Phase 5 Gate Decision Record

**Date:** 2026-09-08  
**Phase:** Phase 5 — Architecture Specification / Gate Closure  
**Overall verdict:** REWORK REQUIRED  
**Architecture frozen:** NO

---

## Gate A — Durable Recovery

**Decision: PASS**

Durable Run creation, Step execution, checkpoint persistence, interruption,
restart, recovery, and state preservation were physically tested.

Acceptance criteria were satisfied:

- Run survives process/runtime loss
- completed work is not incorrectly discarded
- incomplete work is recoverable
- durable state remains coherent
- event/recovery state remains coherent

**Disposition:** Accepted.

---

## Gate B — Needle Benchmark

**Decision: REJECT**

Needle was benchmarked on the actual laptop.

Its measured value was insufficient to justify retaining it as a mandatory
local specialist.

**Disposition:**

- Drop Needle as a required v0 dependency.
- Preserve model-agnostic architecture.
- Do not redesign VAJRA around Needle.

This is a candidate rejection, not an architectural failure.

---

## Gate C — Oracle → Kaggle Worker Lifecycle

**Decision: PASS WITH INFRASTRUCTURE LIMITATION**

Gate C's control-plane lifecycle and physical worker path are now proven.

Deterministic lifecycle evidence proves:

- VAJRA retains canonical Run state.
- Worker Jobs are correlated to the correct Attempt.
- Worker results are accepted only through lease/fencing validation.
- Worker disappearance transitions the Run into recovery.
- Recovery can select a replacement worker.
- Oracle-controlled retry creates a new Attempt with a new lease/fencing identity.
- A stale/disappeared worker cannot later mutate canonical Run state.
- The complete lifecycle is covered by `tests/runtime/test_gate_c_worker_lifecycle.py`.

Physical remote evidence also proves the real worker path:

    Laptop VAJRA
        ↓
    Cloudflare tunnel
        ↓
    Kaggle worker
        ↓
    Qwen 2.5 Coder 32B
        ↓
    WorkerResult
        ↓
    Laptop VAJRA

The physical remote test returned:

    status: completed
    correlation_id: gate-c-remote-correlation-001
    response: VAJRA REMOTE 32B OK
    model: qwen2.5-coder:32b
    elapsed_seconds: 1.589

The HTTP worker transport and its protocol tests are committed in:

    36b24d4 feat: add HTTP worker transport

The remaining limitation is infrastructure availability:

- No Oracle VM/control-plane host is currently available.
- Therefore the actual Oracle-hosted deployment topology has not been
  physically demonstrated.
- This is an infrastructure availability limitation, not an unproven
  VAJRA worker lifecycle behavior.

The earlier request-identity propagation issue is resolved. The finalized
protocol preserves the controlling `correlation_id` across the WorkerJob
and WorkerResult boundary.

**Disposition:**

- Accept Gate C control-plane lifecycle evidence.
- Accept the physical Kaggle/Qwen worker-path evidence.
- Do not claim Oracle-hosted physical deployment until an Oracle environment
  is actually available.
- No further Gate C implementation is required before proceeding to 6K.

**Freeze status:** Accepted with infrastructure limitation.

---

## Gate D — Sandbox Isolation

**Decision: PASS**

The Gate D sandbox candidate was evaluated against the required isolation
boundary. gVisor running through Docker's `runsc` runtime is selected as the
v0 sandbox backend.

The tested isolation boundary proves:

- filesystem isolation
- Docker socket isolation
- path traversal protection
- symlink escape protection
- process namespace isolation
- unauthorized localhost access protection
- explicit network denial
- credential-location isolation
- bounded resource enforcement
- authorized command execution through the gVisor backend

The local environment provides:

    gVisor runsc: release-20260817.0
    Docker runtime: runsc
    KVM: available

Real gVisor integration tests passed:

    tests/sandbox/test_gvisor_integration.py
    4 passed

The complete sandbox test suite passed:

    25 passed

Resource-boundary enforcement was initially not proven and the earlier
host-impacting experiment is rejected as acceptance evidence because the host
rebooted and the result was not controlled or attributable.

The backend was subsequently corrected so declared `SandboxSpec.resource_limits`
are translated into explicit Docker limits:

    memory       -> --memory
    memory_swap  -> --memory-swap
    cpus         -> --cpus
    pids_limit   -> --pids-limit

Unsupported resource-limit keys are rejected rather than silently ignored.

An automated backend test verifies that these limits are actually supplied
to the Docker invocation. A controlled real Docker/gVisor memory-boundary
probe also terminated at the configured resource boundary with exit code 137.

The gVisor backend therefore has both:

1. implementation-level resource-limit wiring evidence, and
2. runtime resource-boundary evidence.

Firecracker was previously validated only at host/KVM/API level. Guest boot
and guest isolation were not proven because no suitable kernel/rootfs pair
was available. Firecracker is therefore not selected for v0.

The sandbox abstraction remains mandatory. The selected implementation is
the gVisor backend behind that abstraction; the architecture does not depend
on Docker or `runsc` semantics outside the backend boundary.

**Disposition:**

- Gate D accepted.
- gVisor selected as the v0 sandbox backend.
- Resource limits are part of the sandbox execution boundary.
- Unsupported resource controls are rejected explicitly.
- Firecracker remains an unselected fallback candidate.
- No further Gate D rework is required before Phase 6 final integration.

**Freeze status:** Accepted.

---

## Gate E — ASTRA Safety Extraction

**Decision: PASS WITH LIMITATIONS**

ASTRA v1.10.0-rc1 was used as a reference implementation.

Targeted tracked tests:

    81/81 passed

Proven behavior included:

- detection hardening
- patch safety
- command policy
- checkpoint handling
- mutation/apply safety
- rollback/recovery
- release hardening
- validation/project safety

**Disposition:**

Only proven safety behavior may be adapted.

The ASTRA legacy core must not become a VAJRA dependency.

---

# Overall Phase 5 Decision

| Gate | Decision |
|---|---|
| A — Durable Recovery | PASS |
| B — Needle | REJECT |
| C — Oracle/Kaggle | BLOCKED / INCOMPLETE |
| D — Sandbox | REWORK |
| E — ASTRA Safety | PASS WITH LIMITATIONS |

## Final Decision

**REWORK REQUIRED**

Phase 5 is not closed.

Architecture is not frozen.

The following are accepted as architectural foundations:

- durable Engineering Run
- model-agnostic Model Gateway
- deterministic Policy Engine
- Execution Broker
- isolated execution abstraction
- independent verification
- explicit recovery
- bounded autonomy
- ASTRA safety behavior only where proven

The remaining material blocker is:

1. Gate D — production sandbox/resource-boundary validation.

Gate C is accepted with an infrastructure limitation: Oracle-hosted physical
deployment remains pending because no Oracle environment is currently
available.

No completed gate should be rerun without new evidence or a changed test
condition.

Phase 6 implementation begins only after required gate closure.

