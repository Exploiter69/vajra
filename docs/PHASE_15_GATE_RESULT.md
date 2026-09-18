# Phase 15 — Gate Result

**Status:** COMPLETE / CLOSED

## Roadmap coverage

Phase 15 covers the complete roadmap scope: filesystem, symlink and TOCTOU boundary hardening; credentials and environment isolation; Git hooks and submodule controls; package lifecycle-script controls; network and sandbox restrictions; worker authentication and result/replay identity preservation; prompt-injection boundary detection; malicious-repository admission checks; CPU, memory, disk, network, process, output, model-call and worker-runtime resource controls; and durable run observability across steps, attempts, workers, models, intents, executions, failures, recoveries, verification and evidence.

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

## Final local evidence

The final local gate passed: 9 hardening tests, 652 portable-suite tests with 4 gVisor integration tests deselected, Python compilation, and `git diff --check`. Physical gVisor integration remains environment-specific and is not claimed here.

Physical gVisor validation remains an environment-specific Gate D capability; hosted CI intentionally excludes gvisor_integration.

## Closure

Phase 15 is closed on the basis of the recorded final local gate evidence. No hosted-CI result is fabricated.
