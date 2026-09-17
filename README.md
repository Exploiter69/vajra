# VAJRA

VAJRA is a local-first, model-agnostic autonomous engineering runtime built around durable Engineering Runs, trusted execution, isolated workspaces, deterministic policy, independent verification, recovery, and human control.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram bot, model-hosting platform, or collection of shell scripts.

## Current Status

**Phase 11 — Long-Run Durability + Chaos: COMPLETE / CLOSED.**

Phases 6–9 established the durable execution substrate, autonomous control/truth boundaries, engineering context/workspaces, and independent verification/anti-gaming.

Phase 10 wired those primitives into the first real objective-to-evidence loop:

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

**Operating-cost constraint:** ₹0.00. No paid inference or infrastructure is a project dependency.

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

Implementation:

- `src/vajra/durability/chaos.py` — deterministic chaos scheduling, retry-storm protection and soak metric contracts
- `src/vajra/durability/kill_harness.py` — real disposable-process `SIGKILL` recovery harness
- `src/vajra/durability/soak.py` — real elapsed-time soak runner
- `tests/durability/test_phase11_chaos.py` — Phase 11 safety, divergence, retry and lease coverage
- `tests/durability/test_phase11_harnesses.py` — kill-harness and soak-runner coverage
- `docs/PHASE_11_IMPLEMENTATION.md` — roadmap-to-implementation mapping
- `docs/PHASE_11_GATE_RESULT.md` — formal Phase 11 gate record
- `.github/workflows/phase11-validation.yml` — free hosted validation

Real multi-day soak runs remain operational measurements: accelerated tests never claim equivalence to real elapsed time.

## Phase 10 implementation

- `src/vajra/autonomy/contracts.py` — structured plans, planned intents, progress measurements, reasoning boundary
- `src/vajra/autonomy/loop.py` — bounded autonomous engineering controller
- `tests/autonomy/test_phase10_loop.py` — end-to-end and safety coverage
- `docs/PHASE_10_IMPLEMENTATION.md` — roadmap-to-implementation mapping and closure evidence
- `docs/PHASE_10_GATE_RESULT.md` — formal Phase 10 gate record
- `.github/workflows/phase10-validation.yml` — free hosted validation

The loop preserves the architectural boundary:

> Model proposes → VAJRA decides → Policy authorizes → Broker executes → Sandbox/Workspace contains → Verifier proves → VAJRA records → Controller decides what happens next.

## What Phase 10 adds

- fresh context before reasoning;
- context-bound structured plans;
- proposal-only reasoning provider;
- durable Run/Step/Attempt identities;
- policy authorization before every execution intent;
- broker-only execution;
- worker lease/result acceptance and fencing;
- independently frozen verification;
- durable verification/evidence recording;
- workspace artifact identity;
- deterministic progress measurement;
- bounded no-progress / retry protection;
- recovery-driven re-planning;
- explicit human escalation;
- hard cycle and resource termination;
- evidence-bound promotion and completion.

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

## Frozen Baseline

`v0.1.0` / `fb3cca5` remains the immutable Phase 6 baseline. Later work proceeds on `main` without rewriting or retagging that baseline.
