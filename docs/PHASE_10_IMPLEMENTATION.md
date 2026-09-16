# VAJRA Phase 10 — Real Autonomous Engineering Loop

## Status

**Implementation complete; validation gate pending local execution.**

Phase 10 is the first autonomous engineering milestone in the roadmap. The
roadmap defines the loop as:

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
repeat
```

This implementation maps those stages onto the existing Phase 6–9 safety
substrate rather than introducing a second execution architecture.

## Implementation

### Objective / durable Run

`EngineeringRun` remains the canonical objective/state object. Phase 10 never
creates a parallel task state machine.

### Orient + Context

`ContextEngine` is rebuilt from the current workspace before orientation and
planning. The resulting `ContextBundle` digest is bound into the structured
plan. A plan generated from a different/stale context is rejected.

### Plan

`ReasoningProvider` is a proposal-only interface. It can orient, create a
structured `EngineeringPlan`, and re-plan after recovery. It cannot execute,
verify, authorize policy, mutate Run state, or declare completion.

### Intent

`PlannedIntent` is converted into the existing policy `Intent` only after the
Run has a durable step/attempt identity. Every intent therefore carries
`run_id`, `step_id`, `attempt_id`, and an operation identity.

### Policy

Every intent passes through the existing deterministic `PolicyEvaluator`.
`DENY` and `HUMAN_REQUIRED` never reach the broker. Promotion is also a policy
operation (`PROMOTE_RUN`) and therefore cannot be inferred from model output.

### Execute

The existing `ExecutionBroker` remains the only execution boundary. Phase 10
wraps the local broker execution in the existing worker lease/result acceptance
protocol so execution remains disposable and stale worker results remain
fenced.

### Observe

Execution produces an artifact identity derived from the observed workspace
status/diff. The result is accepted through `WorkerResultAcceptor`, and loop
stage events are appended to the EventStore.

### Verify

The loop runs only a previously frozen `FrozenVerificationPlan` through the
existing `IndependentVerifier`. Worker/model supplied checks are not accepted
as proof. Verification evidence is persisted into canonical Run state.

### Measure progress

Phase 10 records pre/post workspace digests, verification counts, artifact
references and evidence references. The existing `BoundedAutonomy` layer is
fed a deterministic `ProgressObservation`, so repeated non-progress can halt
the loop rather than creating an infinite retry cycle.

### Decide next step

The existing `Controller` and transition authority remain responsible for
legal lifecycle transitions. Phase 10 adds the concrete stage handlers around
that boundary:

- continue to verification after execution;
- move to candidate only after independent verification;
- recover/re-plan after failed acceptance;
- wait for human authority when policy or evidence is insufficient;
- stop on terminal state or hard cycle/budget limits;
- promote only after acceptance, artifact evidence, verification evidence and
  explicit promotion policy approval.

### Repeat / recovery

Failed execution or failed acceptance enters the existing `RECOVERING` state.
The reasoning provider receives fresh context and must produce a new
context-bound plan. The loop therefore does not blindly repeat an old intent.

## Safety properties preserved

Phase 10 does **not** weaken any earlier architectural law:

- model/reasoning output is never authority;
- canonical Run state remains durable;
- meaningful execution is routed through Policy + Broker;
- worker results are fenced and accepted before becoming canonical;
- verification is independent;
- evidence is required for completion;
- promotion is policy-authorized;
- stale context is rejected;
- no-progress and budget limits can stop autonomous continuation;
- human escalation is explicit;
- the loop has a hard cycle bound;
- Oracle, paid inference, paid hosting and paid infrastructure are not required.

## Test coverage added

`tests/autonomy/test_phase10_loop.py` covers:

1. end-to-end objective → plan → policy → execution → verification → promotion → complete;
2. policy denial/HUMAN_REQUIRED stops autonomous execution;
3. stale context-bound plans are rejected;
4. completion is not assumed before verification/artifact evidence exists;
5. the loop obeys its hard cycle bound;
6. the durable control-plane trace records all major Phase 10 stages.

## Gate

The implementation is not declared Phase 10 **CLOSED** until the repository's
full test suite, Phase 10 tests, compile check and diff check are run locally
and the working tree is clean. This preserves the same evidence standard used
for Gates F and Phase 9.
