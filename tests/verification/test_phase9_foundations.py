from datetime import datetime, timezone
from pathlib import Path

import pytest

from vajra.control.contracts import AcceptanceCriteria, AcceptancePredicate, stable_digest
from vajra.domain.models import VerificationStatus
from vajra.verification.anti_gaming import AntiGamingGuard, AntiGamingStatus
from vajra.verification.environment import VerificationEnvironment, VerificationEnvironmentError
from vajra.verification.independent import IndependentVerifier
from vajra.verification.integrity import TestIntegrityAuditor
from vajra.verification.plan import AcceptanceCriteriaCompiler, CriterionKind


def frozen_criteria(objective: str = "run checks", *, kinds: tuple[str, ...] = ("COMMAND_EXIT",)) -> AcceptanceCriteria:
    return AcceptanceCriteria(
        criteria_id="criteria-1",
        version="1",
        objective_digest=stable_digest(objective),
        predicates=tuple(AcceptancePredicate(f"predicate-{i}", "1", f"criterion {i}") for i in range(1, len(kinds) + 1)),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        frozen_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
    )


def test_acceptance_compiler_requires_frozen_criteria() -> None:
    criteria = AcceptanceCriteria(
        criteria_id="criteria-1",
        version="1",
        objective_digest=stable_digest("run checks"),
        predicates=(AcceptancePredicate("tests", "1", "tests pass"),),
    )
    with pytest.raises(ValueError, match="must be frozen"):
        AcceptanceCriteriaCompiler().compile("run checks", criteria, [{"predicate_id": "tests", "kind": "COMMAND_EXIT", "command": ["pytest", "-q"], "expected_exit_code": 0}])


def test_acceptance_compiler_freezes_machine_checkable_plan() -> None:
    objective = "run checks"
    plan = AcceptanceCriteriaCompiler().compile(
        objective,
        frozen_criteria(objective),
        [{"predicate_id": "predicate-1", "kind": "COMMAND_EXIT", "command": ["pytest", "-q"], "expected_exit_code": 0}],
    )
    assert plan.checks[0].kind is CriterionKind.COMMAND_EXIT
    assert plan.checks[0].parameters == (("command", ("pytest", "-q")), ("expected_exit_code", 0))
    assert len(plan.integrity_digest) == 64


def test_acceptance_compiler_supports_all_roadmap_check_kinds() -> None:
    objective = "verify repository"
    specs = [
        {"predicate_id": "predicate-1", "kind": "COMMAND_EXIT", "command": ["pytest", "-q"], "expected_exit_code": 0},
        {"predicate_id": "predicate-2", "kind": "FILE_EXISTS", "path": "src/app.py"},
        {"predicate_id": "predicate-3", "kind": "FILE_CONTAINS", "path": "src/app.py", "needle": "def main"},
        {"predicate_id": "predicate-4", "kind": "GIT_CLEAN"},
    ]
    criteria = frozen_criteria(objective, kinds=tuple(spec["kind"] for spec in specs))
    plan = AcceptanceCriteriaCompiler().compile(objective, criteria, specs)
    assert tuple(check.kind for check in plan.checks) == (
        CriterionKind.COMMAND_EXIT,
        CriterionKind.FILE_EXISTS,
        CriterionKind.FILE_CONTAINS,
        CriterionKind.GIT_CLEAN,
    )


def test_acceptance_compiler_rejects_unsafe_file_path() -> None:
    objective = "check file"
    with pytest.raises(ValueError, match="safe relative path"):
        AcceptanceCriteriaCompiler().compile(
            objective,
            frozen_criteria(objective),
            [{"predicate_id": "predicate-1", "kind": "FILE_EXISTS", "path": "../secret"}],
        )


def test_pristine_environment_has_no_worker_access() -> None:
    environment = VerificationEnvironment(
        workspace=Path("/tmp/workspace"),
        environment=(("PATH", "/usr/bin"),),
        network_enabled=False,
        sandbox_id="sandbox-1",
    )
    assert environment.worker_access is False
    assert environment.env_dict() == {"PATH": "/usr/bin"}


def test_network_disabled_environment_requires_sandbox() -> None:
    with pytest.raises(VerificationEnvironmentError, match="isolated sandbox"):
        VerificationEnvironment(workspace=Path("/tmp/workspace"), network_enabled=False)


def test_integrity_detects_deleted_and_modified_protected_inputs(tmp_path: Path) -> None:
    path = tmp_path / "verify.py"
    path.write_text("assert True\n", encoding="utf-8")
    auditor = TestIntegrityAuditor()
    baseline = auditor.snapshot(tmp_path, ["verify.py"], revision="r1")
    path.write_text("assert False\n", encoding="utf-8")
    report = auditor.audit(tmp_path, ["verify.py"], baseline, baseline_revision="r1")
    assert not report.valid
    assert {violation.rule for violation in report.violations} == {"protected_file_modified"}

    path.unlink()
    report = auditor.audit(tmp_path, ["verify.py"], baseline, baseline_revision="r1")
    assert any(v.rule == "protected_file_missing" for v in report.violations)


def test_integrity_detects_test_bypass_patterns(tmp_path: Path) -> None:
    path = tmp_path / "verify.py"
    path.write_text("import pytest\npytest.skip('hide failure')\n", encoding="utf-8")
    report = TestIntegrityAuditor().audit(tmp_path, ["verify.py"], {}, baseline_revision="r1")
    assert not report.valid
    assert any(v.rule == "test_skip" for v in report.violations)


class FakeExecutor:
    def __init__(self, output: str = "ok\n") -> None:
        self.commands: list[tuple[str, ...]] = []
        self.output = output

    def execute(self, command: tuple[str, ...], environment: VerificationEnvironment) -> tuple[int, str]:
        self.commands.append(tuple(command))
        assert environment.worker_access is False
        return 0, self.output


def test_independent_verifier_uses_only_frozen_plan_and_seals_evidence() -> None:
    objective = "run checks"
    plan = AcceptanceCriteriaCompiler().compile(
        objective,
        frozen_criteria(objective),
        [{"predicate_id": "predicate-1", "kind": "COMMAND_EXIT", "command": ["pytest", "-q"], "expected_exit_code": 0}],
    )
    executor = FakeExecutor()
    report = IndependentVerifier(executor).verify(
        plan,
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        environment=VerificationEnvironment(
            workspace=Path("/tmp/workspace"),
            environment=(("PATH", "/usr/bin"),),
            network_enabled=True,
        ),
    )
    assert executor.commands == [("pytest", "-q")]
    assert report.verification_results[0].status is VerificationStatus.PASSED
    assert report.verification_results[0].verification_id == "criteria-1:1"
    assert report.verification_results[0].evidence_refs
    assert report.evidence[0].output_digest


def test_independent_verifier_checks_filesystem_observations(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    objective = "verify repository"
    specs = [
        {"predicate_id": "predicate-1", "kind": "FILE_EXISTS", "path": "app.py"},
        {"predicate_id": "predicate-2", "kind": "FILE_CONTAINS", "path": "app.py", "needle": "def main"},
    ]
    criteria = frozen_criteria(objective, kinds=("FILE_EXISTS", "FILE_CONTAINS"))
    plan = AcceptanceCriteriaCompiler().compile(objective, criteria, specs)
    report = IndependentVerifier(FakeExecutor()).verify(
        plan,
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        environment=VerificationEnvironment(workspace=tmp_path, environment=(), network_enabled=True),
    )
    assert [result.status for result in report.verification_results] == [VerificationStatus.PASSED, VerificationStatus.PASSED]


def test_anti_gaming_guard_blocks_missing_evidence_and_wrong_verifier() -> None:
    report = AntiGamingGuard().inspect_verification_claim(
        status="PASSED",
        evidence_present=False,
        verifier_version="attacker",
        expected_verifier_version="independent-verifier-v1",
        artifact_digest_matches=False,
    )
    assert report.status is AntiGamingStatus.BLOCK
    assert {finding.rule for finding in report.findings} == {"missing_evidence", "verifier_identity", "artifact_binding"}
