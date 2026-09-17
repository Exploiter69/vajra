# Phase 12 — Model + Worker Routing

## Status

**COMPLETE — implementation and automated gate validation.**

Phase 12 follows the Phase 11 durability/chaos gate. It adds a model-agnostic gateway, deterministic complexity/capability routing, model/worker fallback planning, and explicit routing evidence without moving authority into the routing layer.

## 12A — Model abstraction

Implemented in `src/vajra/routing/`:

- stable `ModelGateway` contract;
- `ModelRequest` with run/step/attempt identity, task, context, tools, output schema, budget, deadline, selected model, and strategy;
- `ModelResult` with status, structured output, raw output reference, usage, model identity, errors, and routing evidence;
- `ModelIdentity` records provider, model, version, and adapter;
- `ModelUsage` records model calls, token counts, runtime, and cost units;
- `ModelRegistry` and dependency-free `CallableModelAdapter` keep transports replaceable.

No vendor SDK or paid service is required. Local transports and remote worker transports can be registered behind the same boundary later.

## 12B — Complexity routing

`CapabilityRouter` classifies work into:

- `simple`
- `mechanical`
- `complex`
- `difficult`

Workers are selected from advertised capabilities rather than GPU/vendor names. Selection checks task support, required capabilities, preferred model, availability, and budget, then uses deterministic capability/reliability/latency/cost/identity ordering.

The router emits `RoutingDecision` and `RoutingEvidence`, including every eligible candidate and the selected worker/model identity.

## 12C — Model switching

`RoutingRecovery` implements the bounded recovery sequence:

1. same-model retry;
2. different strategy;
3. different model;
4. different worker;
5. human escalation when alternatives are exhausted.

Routing recovery is advisory. Any resulting attempt must still pass the existing durable Run, lease, Policy, Execution Broker, and Verification boundaries.

## 12D — Capability-based workers

`WorkerCapabilities` contains exactly the roadmap capability dimensions:

- accelerator;
- VRAM;
- system RAM;
- model;
- model version;
- context limit;
- supported tasks;
- sandbox type;
- network policy.

`WorkerDescriptor` additionally records availability, reliability, latency, budget cost, and provider/adapter metadata. No specific accelerator is hard-coded.

## Safety invariants

- Routing never authorizes execution.
- Routing never mutates canonical Run state.
- Model output remains non-authoritative.
- Worker self-report is not verification evidence.
- Worker identity is separate from model identity.
- Budget limits are enforced during selection.
- Exhausted routing alternatives escalate instead of looping indefinitely.
- Candidate/selection evidence is explicit and correlated to the request.
- Phase 12 introduces no paid infrastructure or inference dependency.

## Validation

`tests/routing/test_phase12_routing.py` covers:

- model identity/version and usage recording;
- gateway success and adapter failure handling;
- unknown-model rejection;
- complexity classification;
- capability fit;
- deterministic selection;
- budget enforcement;
- fail-closed capability mismatch;
- routing evidence completeness;
- different-model recovery;
- different-worker recovery;
- bounded same-model retry;
- strategy change before resource switching;
- human escalation after exhaustion;
- budget contract validation.

The Phase 12 workflow additionally runs the complete portable test suite, compilation, and `git diff --check`.

## Explicit non-goals

Phase 12 does **not** make Oracle mandatory, does not require a paid provider, does not make Kaggle canonical, does not introduce an always-on daemon, and does not let a router bypass Policy, Execution, leases, or Verification. Those concerns remain bounded by the roadmap's later phases and existing architecture.
