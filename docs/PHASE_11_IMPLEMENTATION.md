# VAJRA Phase 11 — Long-Run Durability + Chaos

## Status

**IMPLEMENTED / VALIDATED / CLOSED**

Phase 11 is the roadmap reliability milestone: prove that VAJRA can continue
or stop safely under sustained failure rather than merely completing a happy
path. The canonical roadmap requires kill testing, state-divergence testing,
retry-storm protection, lease chaos, and long-duration observation.

The implementation is complete at the scope permitted by the available
infrastructure. Real elapsed-time soak execution is exposed as a reusable
runner; accelerated tests validate its mechanics but never claim equivalence
to the requested real durations.

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

`FaultInjector` produces a seeded, reproducible schedule and never mutates
canonical state. `KillHarness` adds a real process boundary: for every named
failure domain it starts a disposable child, durably records the execution,
terminates the child with `SIGKILL`, restarts from the journal, and verifies the
execution is recoverable. This validates the shared VAJRA durability boundary
across all seven failure-domain labels.

This is intentionally distinguished from physical failure of external
infrastructure: the harness proves VAJRA recovery semantics for each modeled
domain, while the actual host/network/sandbox/machine implementation remains
an environment-specific concern.

### 11B — State divergence

The phase verifies that changes to independent reality signals produce a new
digest. Existing Phase 7 `RealityObserver` remains the canonical
reconciliation boundary; Phase 11 does not create a second truth system.

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

`SoakRunner` now provides a real elapsed-time execution mechanism with
monotonic timing, configurable sampling, Linux RSS measurement, workspace
disk measurement, and runtime-supplied counters for:

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
The runner can execute the exact roadmap duration when an operator chooses to
start that profile on available infrastructure.

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

The Phase 11 suite additionally exercises the real `SIGKILL` recovery harness
for all seven modeled kill domains and the real-duration soak runner using a
fake monotonic clock for deterministic unit validation.

The physical gVisor tests remain separately environment-specific and are not
converted into hosted-CI proof.

## Closure rule

Phase 11 is closed when the implementation, chaos/recovery suite, portable
repository suite, compile validation, and diff validation pass. Real 1h/12h/
3d/7d/30d elapsed-time campaigns are operational runs rather than requirements
to hold the source tree hostage for thirty days; their results must be recorded
separately and must not be fabricated from accelerated tests.
