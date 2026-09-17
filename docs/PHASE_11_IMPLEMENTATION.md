# VAJRA Phase 11 — Long-Run Durability + Chaos

## Status

**IMPLEMENTED / VALIDATED / CLOSED**

Phase 11 is the roadmap's reliability milestone: prove that VAJRA can continue
or stop safely under sustained failure rather than merely completing a happy
path. The canonical roadmap requires kill testing, state-divergence testing,
retry-storm protection, lease chaos, and long-duration observation.

## Roadmap coverage

### 11A — Kill testing

The deterministic chaos plan covers every roadmap kill target:

- controller
- worker
- model
- process
- network
- sandbox
- machine simulation

The plan is seeded and reproducible so a failing schedule can be replayed.

A real child-process kill test exercises `LocalDurableRuntime.start_execution`,
process termination, restart, recovery discovery and completion.

### 11B — State divergence

The phase records independent reality signals and verifies that a changed
reality digest differs from the prior trusted observation. Existing Phase 7
`RealityObserver` remains the canonical reconciliation boundary; Phase 11 does
not create a second truth system.

The invariant remains:

`durable state + Git + filesystem + verification → reconciliation → trusted current state`

### 11C — Retry storms

`RetryStormGuard` provides a deterministic per-run/per-step/per-failure
threshold. Repeated identical failures become a termination decision at the
threshold; the guard never executes or mutates work itself.

This complements the existing `BoundedAutonomy`, budget, no-progress and
strategy-loop controls.

### 11D — Lease chaos

The integration test creates worker A, replaces its lease with worker B, then
submits A's stale result. `WorkerResultAcceptor` rejects the stale completion
through the existing fencing boundary.

A stale worker therefore cannot overwrite the newer owner.

### 11E — Long-duration runs

The roadmap profiles are represented explicitly:

- 1 hour
- 12 hours
- 3 days
- 7 days
- 30 days

Actual elapsed-duration runs remain infrastructure-dependent. The soak metrics
record:

- memory growth
- disk growth
- event growth
- context growth
- worker leaks
- stale leases
- retry counts
- verification failures/degradation signals
- provider failures
- clock anomalies

No accelerated test is represented as proof of real elapsed-time behavior.

## Safety invariants

Phase 11 preserves all earlier boundaries:

- model is not authority;
- event history is not unquestionable reality;
- fresh reconciliation precedes continuation;
- stale worker completions are fenced;
- retry storms terminate rather than loop forever;
- terminal Runs have no autonomous write path;
- hard budgets and no-progress controls remain active;
- verification remains external;
- human authority remains available;
- Oracle and paid infrastructure remain optional and are not Phase 11
  dependencies.

## Validation

The free GitHub Actions workflow runs:

1. `pytest -q tests/durability`
2. `pytest -q -k 'not gvisor_integration'`
3. `python -m compileall -q src tests`
4. `git diff --check`

The physical gVisor tests remain separately environment-specific and are not
converted into hosted-CI proof.

## Closure rule

Phase 11 is closed only when the Phase 11 suite passes together with the
portable repository suite and static validation. Long-duration profiles are
available for real soak execution; the roadmap explicitly allows those
durations to depend on available infrastructure.
