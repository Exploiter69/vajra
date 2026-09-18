# VAJRA

VAJRA is a local-first, model-agnostic autonomous engineering runtime built around durable Engineering Runs, trusted execution, isolated workspaces, deterministic policy, independent verification, recovery, and human control.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram bot, model-hosting platform, or collection of shell scripts.

## Current Status

**Phase 13 — Always-On Control Plane: IMPLEMENTED / GATE PENDING.**

Phases 6–9 established the durable execution substrate, autonomous control/truth boundaries, engineering context/workspaces, and independent verification/anti-gaming. Phase 10 established the bounded autonomous objective-to-evidence loop. Phase 11 validated durability and chaos behavior before routing was enabled.

Phase 12 adds model/worker routing without changing the authority boundary:

```text
TASK
   ↓
COMPLEXITY
   ↓
CAPABILITY ROUTER
   ↓
MODEL / WORKER SELECTION
   ↓
MODEL GATEWAY
   ↓
MODEL RESULT + ROUTING EVIDENCE
   ↓
POLICY → BROKER → VERIFICATION
```

**Operating-cost constraint:** ₹0.00. No paid inference or infrastructure is a project dependency.

## Phase 13 implementation

- `src/vajra/control_plane/plane.py` — always-on daemon, durable queue dispatch, human controls and scheduler
- `src/vajra/control_plane/store.py` — append-only fsync-backed queue/schedule/control journal with restart recovery
- `src/vajra/control_plane/contracts.py` — control commands and schedule contracts
- `src/vajra/control_plane/api.py` — localhost-by-default HTTP/JSON control surface
- `tests/control_plane/test_phase13_control_plane.py` — Phase 13 gate coverage
- `docs/PHASE_13_IMPLEMENTATION.md` — roadmap-to-implementation mapping
- `.github/workflows/phase13-validation.yml` — free hosted validation

Phase 13 preserves canonical Run ownership and routes all Run mutations through RunManager/TransitionAuthority. `CANCEL` is resumable pause/cancellation; `ABORT` is terminal. Scheduled jobs enter the same durable Run queue rather than becoming an external source of truth.

## Phase 12 implementation

- `src/vajra/routing/contracts.py` — model identity, request/result, usage, task complexity, routing evidence and budget contracts
- `src/vajra/routing/gateway.py` — stable model gateway, registry and dependency-free adapter boundary
- `src/vajra/routing/workers.py` — capability-based worker descriptors and registry
- `src/vajra/routing/router.py` — deterministic complexity/capability/budget routing
- `src/vajra/routing/recovery.py` — bounded same-model/strategy/model/worker/human fallback sequence
- `tests/routing/test_phase12_routing.py` — Phase 12 routing and recovery gate coverage
- `docs/PHASE_12_IMPLEMENTATION.md` — roadmap-to-implementation mapping and closure evidence
- `.github/workflows/phase12-validation.yml` — free hosted validation

Phase 12 deliberately does not make Oracle mandatory, make Kaggle canonical, add paid providers, or permit routing to bypass Policy, Execution Broker, leases, or independent Verification.

## Phase 11 implementation

Phase 11 validates unattended durability under failure rather than only the happy path:

- deterministic kill schedules for controller, worker, model, process, network, sandbox and machine simulation;
- a real `SIGKILL` recovery harness across all seven modeled failure domains;
- state-divergence detection without replacing Phase 7 reconciliation;
- hard retry-storm termination;
- lease-expiry/fencing race coverage;
- explicit 1h / 12h / 3d / 7d / 30d long-run profiles;
- a real elapsed-time `SoakRunner` with monotonic timing and resource measurement;
- soak metrics for memory, disk, events, context, worker leaks, stale leases, retries, verification/provider failures and clock anomalies.

## Phase 10 implementation

- `src/vajra/autonomy/contracts.py` — structured plans, planned intents, progress measurements, reasoning boundary
- `src/vajra/autonomy/loop.py` — bounded autonomous engineering controller
- `tests/autonomy/test_phase10_loop.py` — end-to-end and safety coverage
- `docs/PHASE_10_IMPLEMENTATION.md` — roadmap-to-implementation mapping and closure evidence
- `docs/PHASE_10_GATE_RESULT.md` — formal Phase 10 gate record
- `.github/workflows/phase10-validation.yml` — free hosted validation

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
- `docs/VAJRA_v1_Architecture_and_Roadmap_Specification.md` — converged roadmap
- `docs/CURRENT_STATE.md` — current implementation/gate state
- `docs/PHASE_7_DESIGN_FREEZE.md` — Phase 7 safety/control design freeze
- `docs/PHASE_8_IMPLEMENTATION.md` — context/workspace implementation
- `docs/PHASE_9_IMPLEMENTATION.md` — verification/anti-gaming implementation
- `docs/PHASE_9_GATE_RESULT.md` — Phase 9 closure record
- `docs/PHASE_10_IMPLEMENTATION.md` — Phase 10 implementation and closure evidence
- `docs/PHASE_10_GATE_RESULT.md` — Phase 10 gate closure record
- `docs/PHASE_11_IMPLEMENTATION.md` — Phase 11 implementation and closure evidence
- `docs/PHASE_11_GATE_RESULT.md` — Phase 11 gate closure record
- `docs/PHASE_12_IMPLEMENTATION.md` — Phase 12 implementation and closure evidence
- `docs/PHASE_13_IMPLEMENTATION.md` — Phase 13 implementation and roadmap mapping
- `docs/PHASE_13_GATE_RESULT.md` — Phase 13 gate closure record

## Frozen Baseline

`v0.1.0` / `fb3cca5` remains the immutable Phase 6 baseline. Later work proceeds on `main` without rewriting or retagging that baseline.
