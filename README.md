# VAJRA

VAJRA is a local-first, model-agnostic autonomous engineering-run
system designed around durable Engineering Runs, trusted execution,
isolated workspaces, deterministic policy, verification, recovery,
persistent engineering memory, and human control.

## Current Status

**VAJRA v0 — Phase 5 Gate Rework**

Architecture is **NOT FROZEN**.

### Gate Status

| Gate | Property | Status |
|---|---|---|
| A | Durable Recovery | PASS |
| B | Needle Benchmark | REJECT / DROP NEEDLE |
| C | Oracle → Kaggle Worker Lifecycle | BLOCKED / INCOMPLETE |
| D | Sandbox Isolation | REWORK |
| E | ASTRA Safety Extraction | PASS WITH LIMITATIONS |

Phase 6 implementation begins only after the remaining gates are
resolved according to the VAJRA v0 Technical Specification.

## Architectural Principle

The model is not authority.

```text
MODEL
  │
  │ proposes
  ▼
INTENT
  │
  │ authorize
  ▼
POLICY
  │
  │ permits
  ▼
EXECUTION
  │
  │ produces
  ▼
ARTIFACT
  │
  │ independently verify
  ▼
EVIDENCE
  │
  │ satisfies criteria
  ▼
ENGINEERING PROGRESS
