# VAJRA

VAJRA is a local-first, model-agnostic autonomous engineering runtime designed around durable Engineering Runs, trusted execution, isolated workspaces, deterministic policy, verification, recovery, persistent engineering memory, and human control.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram bot, model-hosting platform, or collection of shell scripts.

## Current Status

**VAJRA v0.1.0 — Phase 6 complete**

The Phase 6 implementation baseline is frozen at commit `fb3cca5` and tagged `v0.1.0`.

**Phase 6 final integration gate:** PASS  
**Test suite at freeze:** 419 passed  
**Working tree at freeze:** clean  
**Operating-cost constraint:** ₹0.00

The v0.1.0 baseline is a hardened runtime foundation. It is **not yet the complete autonomous engineering loop**. The next implementation work is post-v0 operationalization: wiring context, model reasoning, intent generation, execution, verification, and recovery into a durable end-to-end engineering controller.

### Gate Status

| Gate | Property | Status |
|---|---|---|
| A | Durable Recovery | PASS |
| B | Needle Benchmark | REJECT / DROP NEEDLE |
| C | Oracle → Kaggle Worker Lifecycle | PASS WITH INFRASTRUCTURE LIMITATION |
| D | Sandbox Isolation | PASS — gVisor selected for v0 |
| E | ASTRA Safety Extraction | PASS WITH LIMITATIONS |

Gate C is accepted on deterministic Oracle-control lifecycle evidence plus a physical Laptop → Kaggle worker path. An Oracle VM was not available, so an Oracle-hosted deployment itself was not claimed as physically proven.

Gate D selected gVisor through Docker/runsc for the v0 sandbox boundary. Firecracker was not selected because guest boot/isolation could not be proven in the available environment. The SandboxBackend abstraction remains mandatory.

## What v0.1.0 Contains

- Core domain contracts
- Engineering Run lifecycle
- Durable runtime abstraction and restart-capable reference runtime
- Durable Steps and disposable Attempts
- Worker Job/Result protocol
- Lease and fencing authority
- Worker-result acceptance boundary
- Deterministic Policy Engine
- Execution Broker
- Bounded workspace file/process/Git execution boundaries
- Independent verification
- Structured verification evidence
- Failure classification and recovery policy
- Retry, strategy/model/worker recovery actions
- Checkpoints and reconciliation
- Human escalation and Run abort control
- CLI human control surface
- gVisor sandbox backend and security validation
- Kaggle worker integration path
- Comprehensive automated test coverage

## Architecture

The fundamental guarantee is:

> A worker, model, process, network connection, or machine may disappear without destroying the Engineering Run.

Canonical state belongs to VAJRA, not to models or workers.

```text
OBJECTIVE
    │
    ▼
CONTEXT
    │
    ▼
MODEL / REASONING
    │ proposes
    ▼
INTENT
    │ authorize
    ▼
POLICY
    │ permits
    ▼
EXECUTION BROKER
    │
    ▼
SANDBOX / WORKSPACE
    │
    ▼
ARTIFACT
    │ independently verify
    ▼
VERIFICATION
    │ produces
    ▼
EVIDENCE
    │
    ▼
NEXT STEP / RECOVERY / COMPLETION
```

The model is inside VAJRA, never above VAJRA. Reasoning proposes; policy authorizes; the Execution Broker executes; verification independently establishes evidence.

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

## Repository Documentation

- `docs/VAJRA_v0_Technical_Specification.txt` — canonical v0 architecture/specification
- `docs/CURRENT_STATE.md` — current implementation and gate status
- `docs/MASTER_CONTEXT.md` — project context and continuity
- `docs/DECISIONS.md` — accepted architectural decisions
- `docs/ROADMAP.md` — implementation roadmap
- `docs/AI_HANDOFF.md` — AI-assisted development handoff

## Frozen Baseline

`v0.1.0` is the Phase 6 completion baseline. Do not rewrite, delete, or retag it. Subsequent work proceeds from `main` as post-v0 operationalization while preserving the architectural laws and the v0 specification.
