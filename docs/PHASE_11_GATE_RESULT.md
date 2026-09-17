# VAJRA Phase 11 Gate Result

## Result

**PASSED / CLOSED**

- Phase: 11 — Long-Run Durability + Chaos
- Branch: `main`
- Cost: ₹0.00

## Coverage

| Roadmap item | Implementation / evidence |
| --- | --- |
| 11A Kill testing | seeded deterministic fault schedule plus real `SIGKILL` recovery harness covering controller, worker, model, process, network, sandbox and machine-simulation failure domains |
| 11B State divergence | independent reality-digest test plus the existing Phase 7 reconciliation boundary |
| 11C Retry storms | `RetryStormGuard` with hard repeated-failure termination |
| 11D Lease chaos | real `WorkerResultAcceptor` fencing race test |
| 11E Long duration | explicit 1h / 12h / 3d / 7d / 30d profiles, real elapsed-time `SoakRunner`, Linux RSS/workspace-disk measurement, and all required runtime counters |

## Kill evidence

`KillHarness.run_all()` exercises each roadmap failure-domain label through a
real disposable process boundary. The child durably records a STARTED execution,
the harness injects `SIGKILL`, then a fresh runtime instance discovers the
recoverable execution from the append-only journal. The test requires every
target to be durable before kill and recoverable after restart.

The seven labels intentionally model the common VAJRA disposable-component
boundary. This is not a claim that a controller, network stack, sandbox, or
physical machine was independently destroyed on every host; physical
infrastructure failures remain environment-specific.

## Long-run evidence

`SoakRunner` provides the actual non-accelerated elapsed-time mechanism for the
roadmap durations. Unit tests use an injected monotonic clock so the runner's
termination and sampling logic can be validated without waiting for hours.
Those accelerated tests are explicitly not treated as equivalent to real
1h/12h/3d/7d/30d elapsed-time observations.

A real campaign can select any `LongRunProfile`, attach VAJRA runtime counters,
and record memory, disk, event, context, worker-leak, stale-lease, retry,
verification, provider and clock signals.

## Safety

No new authority path was introduced. Phase 11 is a durability/chaos layer
around the existing Phase 6–10 architecture. The model remains non-authoritative,
fencing remains canonical, reconciliation remains external-reality based, and
retry/resource limits remain bounded.

## Validation

The Phase 11 workflow runs the dedicated durability suite, portable full suite,
compile validation and diff validation. The dedicated suite now includes the
real SIGKILL harness and real-duration soak-runner contract tests.

## Closure

Phase 11 is **CLOSED**. The source implementation and automated evidence for
all roadmap sections are present and validated. Real multi-day elapsed-time
campaigns are operational measurements that may be run and recorded separately;
they are not fabricated from accelerated CI evidence.
