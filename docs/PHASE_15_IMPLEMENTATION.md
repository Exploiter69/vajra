# Phase 15 — Production Hardening

**Status:** IMPLEMENTED / GATE PENDING

Phase 15 is the roadmap's "make it boring" phase. It hardens filesystem/workspace boundaries, hostile repository handling, sandbox execution, model/resource budgets, and human observability without changing VAJRA's authority model.

## Roadmap coverage

### Security

Implemented controls cover every roadmap security category:

- filesystem: workspace paths are resolved and constrained to an optional trusted workspace root; execution uses explicit paths and no shell interpolation.
- symlinks: symlink path components are rejected by the default security policy; repository scans flag symlinks.
- TOCTOU: workspace validation is performed at the execution boundary immediately before dispatch; subprocesses use explicit argv, shell=False, and a dedicated process group. The remaining OS/daemon race cannot be claimed as mathematically eliminated by path validation alone.
- credentials: secret-bearing environment names are rejected; commands referencing common credential locations are rejected; sensitive repository paths are reported.
- Git hooks: executable non-sample Git hooks are rejected by repository scanning.
- submodules: .gitmodules is rejected unless explicitly permitted.
- package scripts: npm lifecycle scripts (preinstall, install, postinstall, prepare) are rejected unless explicitly permitted.
- network: network is disabled by default in the gVisor backend and the security policy rejects network-enabled execution unless explicitly permitted.
- environment variables: only an explicit safe environment allowlist is accepted; secret-looking names are always rejected.
- sandbox: gVisor remains the selected physical sandbox backend; Phase 15 adds security-policy checks plus runtime/output limits around it.
- worker authentication: WorkerAuthenticator adds attempt-bound HMAC proofs with expiry; existing lease/attempt identity and stale-worker rejection remain authoritative.
- result replay: existing attempt/correlation/lease fencing remains authoritative; audit identities are deterministic and duplicate-protected.
- prompt injection: untrusted text can be classified and rejected when it contains common instruction-override indicators. This is a boundary detector, not a claim of perfect semantic detection.
- malicious repositories: admission scans symlinks, submodules, sensitive paths, executable hooks, and package lifecycle scripts before worktree creation.

### Resource controls

ResourceLimits and ResourceGovernor provide deterministic fail-closed accounting for CPU, memory, disk, network, process count, output, model calls, and worker runtime.

The gVisor backend enforces CPU, memory, process-count, wall-clock runtime, and output limits at the sandbox process boundary. Network is disabled by default. Model calls, measured model output bytes, and reported worker runtime can be charged through ResourceGovernor; disk/network byte accounting is available as an explicit authority-bound budget and is never falsely treated as enforced when an execution backend cannot measure it.

A resource charge is atomic: if any requested charge would exceed a limit, none of the charge is committed.

### Observability

AuditStore is an append-only, fsync-backed, tamper-evident audit journal. AuditLoopObserver connects bounded autonomous-loop observations to the audit journal. Observability.explain() exposes a run-oriented view containing Run, steps, attempts, workers, models, intents, executions, failures, recoveries, verification, and evidence.

The audit layer is observational only. It does not own canonical Run state or authorize operations.

## Authority preservation

Phase 15 does not change the canonical authority chain:

model/reasoning → intent → policy → execution broker → sandbox/workspace → independent verification → evidence → controller/human

Hardening may reject unsafe work, but it cannot authorize work that Policy did not authorize.

## Zero-cost boundary

Phase 15 adds no paid dependency, hosted service, model, database, or infrastructure requirement. Validation uses Python standard-library components plus the repository's existing pytest test runner.

## Validation

The Phase 15 workflow runs dedicated hardening tests, the portable full suite with gVisor integration excluded, Python compilation, and git diff checking.

Final closure requires those checks to pass on the final main revision. Hosted CI results are recorded only when independently observable.
