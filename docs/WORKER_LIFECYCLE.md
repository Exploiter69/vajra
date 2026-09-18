# VAJRA Worker Lifecycle Boundary

VAJRA separates worker lifecycle from the model gateway.

## Control path

WorkerProvider -> ManagedWorkerProvider -> readiness -> lease -> ModelGateway -> model

The lifecycle coordinator owns the control-plane lifecycle. Provider-specific
code supplies only the mechanics needed to start and release a runtime.

The model cannot start, stop, lease, replace, or approve a worker.

## Implemented boundary

ManagedWorkerProvider provides:

- provider start invocation;
- bounded readiness polling;
- readiness through the existing WorkerProvider contract;
- an immutable lease record;
- revalidation before reuse;
- explicit release;
- typed lifecycle failures.

## Kaggle reality

The Kaggle CLI can push a kernel and trigger a kernel run, but that is a batch
execution contract, not a guarantee that a Kaggle localhost HTTP server becomes
reachable from VAJRA. Kaggle's notebook documentation describes remote notebook
sessions, while Kaggle's current material also documents limitations around
accessing notebook ports.

Therefore VAJRA does not report READY merely because a Kaggle kernel was
scheduled. A Kaggle provider may start a runtime, but it must not return a
ready WorkerEndpoint until /health, /capabilities, and /infer are independently
reachable.

This prevents a false READY state from allowing a model call across an
unverified infrastructure boundary.

## Zero-cost operating modes

1. Local worker: fully unattended while the laptop is running.
2. Kaggle burst worker: start the validated Qwen/T4 runtime through Kaggle
   tooling where available, then use it only after endpoint readiness is
   independently proven.
3. Future provider: implement start/stop against a provider exposing a stable
   programmatic runtime and reachable endpoint.

No paid tunnel, hosted gateway, or proprietary control plane is required by
this abstraction.

## Remaining physical gate

The remaining Kaggle-specific gate is operational:

1. start the Kaggle worker runtime;
2. make the HTTP worker endpoint reachable;
3. prove /health;
4. prove /capabilities;
5. run VAJRA Run #3;
6. record lifecycle and endpoint evidence.

Only then should a Kaggle-specific lifecycle adapter be marked capable of
unattended live inference.
