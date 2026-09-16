# VAJRA Phase 9 — Verification + Anti-Gaming

**Status:** Implementation complete; executable validation gate pending
**Baseline:** Phase 8 complete at 565 tests, clean compile/diff/worktree
**Operating-cost constraint:** ₹0.00

## Roadmap coverage

Phase 9 is implemented against the canonical roadmap requirements:

1. **9A — Acceptance Criteria Compiler**: frozen acceptance criteria compile into a deterministic machine-checkable verification plan. Natural-language text is never silently promoted into executable authority; explicit executable specifications are required.
2. **9B — Independent Verifier**: verification executes only a frozen plan through an executor boundary. Worker/model output cannot choose or rewrite verification checks. Command, filesystem, and Git-clean checks are supported.
3. **9C — Test Integrity**: protected verification inputs are snapshotted and audited for deletion/modification; bypass patterns such as skip/xfail/monkeypatch/mock usage are detected in protected Python verification inputs.
4. **9D — Pristine Verification Environment**: verification receives an explicit absolute workspace, exact environment allowlist, timeout, worker-access prohibition, and sandbox requirement when network is disabled. The local subprocess executor refuses network-disabled execution unless an isolated sandbox executor is supplied.
5. **9E — Evidence Integrity**: verification observations are sealed into structured evidence containing check identity, command, status, exit code, output reference/digest, environment, timestamp, verifier identity, and content digest.
6. **9F — Adversarial Verification**: the anti-gaming guard fails closed for missing evidence, verifier identity mismatch, artifact binding mismatch, non-canonical statuses, and verification-input integrity violations.

## Safety properties

- Acceptance criteria must be frozen before compilation.
- Acceptance criteria are bound to the objective digest.
- Verification plans are immutable and content-digested.
- Verification commands are taken from the frozen plan, never from worker output.
- Verification does not authorize or mutate Run lifecycle state.
- Passed verification receives evidence before it can satisfy the existing acceptance evaluator.
- Network-disabled verification requires an isolated sandbox executor.
- Worker access is prohibited by the verification environment contract.
- Protected verification inputs fail closed when changed or deleted.
- `INCONCLUSIVE` is never treated as success.
- Phase 7 authority boundaries remain in force.
- Phase 10 autonomous loop remains disabled.

## Validation gate

The phase is not closed until the local checkout demonstrates:

```text
pytest -q tests/verification tests/control
pytest -q
python -m compileall -q src tests
git diff --check
git status --short
```

The final Phase 9 result must record observed counts and zero failures only after those commands have actually been run in the repository checkout.
