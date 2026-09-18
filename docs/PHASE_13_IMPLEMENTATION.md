# Phase 13 — Always-On Control Plane

**Status:** COMPLETE / CLOSED

This phase implements every Phase 13 subsection in the canonical roadmap:

- **13A — Daemon:** a restart-aware control-plane daemon with a bounded polling loop and clean stop semantics.
- **13B — Queue:** an append-only, fsync-backed durable queue journal with FIFO-ready selection, dispatch claims, crash recovery of in-flight claims, completion, cancellation, and requeue after executor failure.
- **13C — Cancellation / human control:** pause, resume, cancel, abort, retry, approve, and reject are explicit control commands. Run mutations go through RunManager and TransitionAuthority; the control plane never mutates EngineeringRun objects directly.
- **13D — Scheduling:** one-shot and periodic schedules are persisted in the same control-plane journal. Schedule handlers create durable Runs; periodic schedules advance their next due time without using external cron as source of truth. The scheduler also supports background-job handlers.
- **13E — API:** a dependency-free localhost-by-default HTTP/JSON control surface exposes health, queue, schedules, run status, submission, all seven human commands, and schedule cancellation. It is a replaceable control surface; it does not own Run state and does not make Telegram a dependency.

## Safety boundaries

1. Canonical Run state remains owned by the existing StateStore / RunManager.
2. Human commands are routed through TransitionAuthority.
3. The API is bound to 127.0.0.1 by default; callers must explicitly opt into another bind address.
4. Queue dispatch claims are durable. A process crash after claim reopens the entry on the next control-plane instance.
5. Executor failure requeues the entry instead of losing the Run.
6. PAUSED is terminal for the current autonomous-loop invocation; the Phase 10 loop no longer converts a human pause back into recovery automatically.
7. CANCEL is a resumable cancellation/pause of queued or active work; ABORT is terminal.
8. Schedules create queue entries only through registered handlers, so scheduled work still enters the normal Run/policy/execution/verification chain.
9. No model, worker, Telegram client, external cron, or HTTP client can become canonical state authority.

## Cost / dependency boundary

The implementation uses only Python standard-library facilities. No paid service, hosted dependency, database service, or external scheduler is required.

## Validation

The Phase 13 test suite covers restart/recovery of dispatching queue entries; FIFO submission and durable completion; executor failure and requeue; pause/cancel/abort; active-run pause/resume; failed-run retry; approval/rejection; one-shot and periodic scheduling; daemon start/stop; and the localhost HTTP control surface.

The Phase 13 workflow runs the Phase 13 suite, the portable full suite, compilation, and git diff checking.

The corresponding gate closure is recorded in `docs/PHASE_13_GATE_RESULT.md` (GitHub Actions run `35300794216`).

Phase 13 does not add Engineering Memory, production hardening, Kubernetes, multi-agent behavior, or a Telegram-specific runtime. Those remain later roadmap concerns.
