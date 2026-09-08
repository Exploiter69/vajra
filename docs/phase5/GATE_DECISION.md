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

**Decision: BLOCKED / INCOMPLETE**

Kaggle-side infrastructure, Ollama, model inference, connectivity, worker
protocol behavior, and coding-task execution were exercised.

The canonical Oracle-controlled lifecycle was not fully tested because the
Oracle environment/account was unavailable.

Unproven acceptance requirements:

- Oracle retains canonical Run state
- worker loss does not destroy the Run
- result is correctly correlated to Attempt
- stale worker cannot mutate the Run
- retry/recovery is controlled by Oracle

A protocol test also identified request-identity propagation as an issue:
the disposable worker generated its own request identifier instead of
preserving the controlling request identifier.

**Disposition:** Return to Gate C when Oracle is available.

**Freeze status:** Not frozen.

---

## Gate D — Sandbox Isolation

**Decision: REWORK**

gVisor proved substantial isolation:

- filesystem isolation
- Docker socket isolation
- path traversal protection
- symlink escape protection
- process namespace isolation
- unauthorized localhost access protection
- explicit network denial
- credential-location isolation

The required resource boundary was not proven.

Host:

    CgroupVersion=2
    CgroupDriver=systemd

gVisor:

    cgroup v1=true
    cgroup v2=false
    systemd=false
    systemdUser=false

Docker-provided resource limits were not demonstrated inside the tested
gVisor configuration.

A controlled resource-limit startup attempt failed with:

    cannot create sandbox: cannot read client sync file:
    waiting for sandbox to start: EOF

The earlier host-impacting resource experiment is rejected as acceptance
evidence because the host rebooted and the result was not controlled or
attributable.

Firecracker was validated only at host/KVM/API level. Guest boot and guest
isolation were not proven because no suitable kernel/rootfs pair was
available.

**Disposition:**

- Current gVisor configuration is not frozen.
- Firecracker is not claimed as validated.
- Sandbox abstraction remains mandatory.
- Gate D requires rework before freeze.

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

The only remaining material blockers are:

1. Gate C — complete Oracle-controlled worker lifecycle.
2. Gate D — production sandbox/resource-boundary validation.

No completed gate should be rerun without new evidence or a changed test
condition.

Phase 6 implementation begins only after required gate closure.

