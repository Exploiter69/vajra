# Phase 15 — Gate Result

**Status:** IMPLEMENTED / GATE PENDING

## Roadmap coverage

Phase 15 covers the complete roadmap scope: filesystem, symlink and TOCTOU boundary hardening; credentials and environment isolation; Git hooks and submodule controls; package lifecycle-script controls; network and sandbox restrictions; worker/result identity preservation; prompt-injection boundary detection; malicious-repository admission checks; CPU, memory, disk, network, process, output, model-call and worker-runtime resource controls; and durable run observability across steps, attempts, workers, models, intents, executions, failures, recoveries, verification and evidence.

## Implementation

- src/vajra/hardening/contracts.py
- src/vajra/hardening/security.py
- src/vajra/hardening/audit.py
- src/vajra/hardening/__init__.py
- tests/hardening/test_phase15_hardening.py
- gVisor sandbox hardening in src/vajra/sandbox/gvisor.py
- repository admission hardening in src/vajra/control/worktree.py
- model resource charging in src/vajra/routing/gateway.py
- .github/workflows/phase15-validation.yml

## Evidence boundary

Phase 15 is not closed until the final validation commands pass on the final repository revision. No test or hosted-CI result is fabricated in this document.

Physical gVisor validation remains an environment-specific Gate D capability; hosted CI intentionally excludes gvisor_integration.

## Closure rule

When the final dedicated suite, portable full suite, compilation, and diff checks pass, this document may be changed to COMPLETE / CLOSED with the exact observed evidence.
