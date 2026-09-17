# VAJRA Phase 11 Gate Result

## Result

**PASSED / CLOSED — implementation and automated gate**

- Phase: 11 — Long-Run Durability + Chaos
- Branch: `main`
- Cost: ₹0.00

Closure means the Phase 11 source, automated evidence, and free portable validation are complete. It does **not** manufacture evidence for real elapsed-time campaigns that have not actually been run.

## Coverage

| Roadmap item | Implementation / evidence |
| --- | --- |
| 11A Kill testing | seeded deterministic fault schedule; real `SIGKILL` recovery harness; explicit recovery semantics for all seven modeled failure domains |
| 11B State divergence | real temporary Git repository + filesystem mutation observed through the existing `RealityObserver` and `filesystem_digest` |
| 11C Retry storms | `RetryStormGuard` plus actual `LocalDurableRuntime.retry()` journal-boundary hard-stop test |
| 11D Lease chaos | real `WorkerResultAcceptor` fencing race test |
| 11E Long duration | exact 1h / 12h / 3d / 7d / 30d profiles, real elapsed-time `SoakRunner`, Linux RSS/workspace-disk measurement, all required runtime counters, persisted JSON evidence format |

## 11A — Kill evidence

`KillHarness.run_all()` exercises each roadmap failure-domain label through a
real disposable process boundary. The child durably records a STARTED execution,
the harness injects `SIGKILL`, then a fresh runtime instance discovers the
recoverable execution from the append-only journal.

The result also records explicit recovery semantics:

- controller → restart component and reconcile;
- worker → restart component and reconcile;
- model → retry reasoning with fresh context;
- process → restart process and recover;
- network → reconnect and reconcile external state;
- sandbox → discard sandbox and reconcile workspace;
- machine simulation → restore durable state and reconcile.

Network, sandbox and machine-simulation are **modeled** domains in this free
portable harness. This is not a claim that host networking, a physical sandbox,
or the machine itself were independently destroyed. Such physical campaigns are
environment-specific.

## 11B — State-divergence evidence

The Phase 11 test creates an actual Git repository, records its clean revision,
status and filesystem digest through the existing reconciliation primitives,
mutates a tracked file, and observes the resulting Git/filesystem divergence.
The existing `RealityObserver` remains the canonical truth/reconciliation
boundary; Phase 11 introduces no competing truth system.

## 11C — Retry-storm evidence

The isolated guard remains useful for deterministic signature-level protection,
but the gate also exercises the actual `LocalDurableRuntime` retry path. After
the configured retry budget is exhausted, a further retry is rejected rather
than executing the operation.

## 11D — Lease evidence

Worker A's lease is replaced by worker B's fencing position. A's stale result is
submitted to the real `WorkerResultAcceptor` and is rejected. No stale worker
can overwrite the newer owner through that acceptance boundary.

## 11E — Long-run evidence

`SoakRunner` uses a monotonic clock and supports exact configured elapsed
campaigns. It measures or accepts counters for:

- memory growth
- disk growth
- event growth
- context growth
- worker leaks
- stale leases
- retry counts
- verification failures/degradation
- provider failures
- clock anomalies

`run_and_write()` persists configured duration, sampling interval, completion
elapsed time, and all samples as JSON evidence.

The automated suite uses an injected clock so tests finish immediately. Those
accelerated tests validate runner mechanics only and are **not equivalent** to
real 1h/12h/3d/7d/30d elapsed-time observations. A real campaign must be run for
the selected duration and its JSON evidence retained separately.

## Safety

No new authority path was introduced. Phase 11 remains a durability/chaos layer
around the existing Phase 6–10 architecture. The model remains non-authoritative,
fencing remains canonical, reconciliation remains external-reality based, and
retry/resource limits remain bounded.

## Validation

The free GitHub Actions workflow runs:

1. `pytest -q tests/durability`
2. `pytest -q -k 'not gvisor_integration'`
3. `python -m compileall -q src tests`
4. `git diff --check`

The workflow intentionally does not claim physical gVisor validation; Gate D
remains separately environment-specific.

## Closure

Phase 11 is **CLOSED for implementation and automated validation**. The
repository now contains the required chaos controls, runtime-boundary tests,
real elapsed-time soak mechanism, and evidence format. Real 1h/12h/3d/7d/30d
campaign results remain operational measurements and must never be fabricated
from accelerated CI runs.
