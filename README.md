# VAJRA

VAJRA is a local-first, model-agnostic autonomous engineering runtime built around durable Engineering Runs, trusted execution, isolated workspaces, deterministic policy, independent verification, recovery, and human control.

VAJRA is not a chatbot, LLM wrapper, IDE, single autonomous agent, Telegram bot, model-hosting platform, or collection of shell scripts.

## Current Status

**Phase 10 — Real Autonomous Engineering Loop: implementation complete; validation gate pending local execution.**

Phases 6–9 established the durable execution substrate, autonomous control/truth boundaries, engineering context/workspaces, and independent verification/anti-gaming.

Phase 10 now wires those primitives into the first real objective-to-evidence loop:

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

**Operating-cost constraint:** ₹0.00. No paid inference or infrastructure is a Phase 10 dependency.

Phase 10 is not declared CLOSED until the Phase 10 tests, full suite, compile check, diff check, and clean working-tree validation have been run locally.

## Phase 10 implementation

- `src/vajra/autonomy/contracts.py` — structured plans, planned intents, progress measurements, reasoning boundary
- `src/vajra/autonomy/loop.py` — bounded autonomous engineering controller
- `tests/autonomy/test_phase10_loop.py` — end-to-end and safety coverage
- `docs/PHASE_10_IMPLEMENTATION.md` — roadmap-to-implementation mapping

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
- `docs/CURRENT_STATE.md` — implementation/gate state
- `docs/PHASE_7_DESIGN_FREEZE.md` — Phase 7 safety/control design freeze
- `docs/PHASE_8_IMPLEMENTATION.md` — context/workspace implementation
- `docs/PHASE_9_IMPLEMENTATION.md` — verification/anti-gaming implementation
- `docs/PHASE_9_GATE_RESULT.md` — Phase 9 closure record
- `docs/PHASE_10_IMPLEMENTATION.md` — Phase 10 implementation and validation gate

## Frozen Baseline

`v0.1.0` / `fb3cca5` remains the immutable Phase 6 baseline. Later work proceeds on `main` without rewriting or retagging that baseline.
