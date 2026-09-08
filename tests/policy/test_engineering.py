import pytest

from vajra.policy import Intent, PolicyDecisionType
from vajra.policy.engineering import (
    ENGINEERING_POLICY_ID,
    ENGINEERING_POLICY_VERSION,
    engineering_policy,
)


def make_intent(
    operation: str,
    capabilities: tuple[str, ...],
) -> Intent:
    return Intent(
        intent_id=f"intent-{operation}",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        requested_capabilities=capabilities,
    )


@pytest.mark.parametrize(
    ("operation", "capability"),
    [
        ("read_file", "workspace.read"),
        ("write_file", "workspace.write"),
        ("run_tests", "execution.test"),
        ("run_build", "execution.build"),
    ],
)
def test_safe_engineering_operations_are_allowed(operation, capability):
    decision = engineering_policy().evaluate(
        make_intent(operation, (capability,))
    )

    assert decision.decision is PolicyDecisionType.ALLOW
    assert decision.policy_id == ENGINEERING_POLICY_ID
    assert decision.policy_version == ENGINEERING_POLICY_VERSION


def test_git_push_requires_human():
    decision = engineering_policy().evaluate(
        make_intent("git_push", ("git.write",))
    )

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED


def test_force_push_is_denied():
    decision = engineering_policy().evaluate(
        make_intent("git_force_push", ("git.write",))
    )

    assert decision.decision is PolicyDecisionType.DENY


def test_repository_deletion_is_denied():
    decision = engineering_policy().evaluate(
        make_intent("delete_repository", ("repository.admin",))
    )

    assert decision.decision is PolicyDecisionType.DENY


def test_production_deployment_requires_human():
    decision = engineering_policy().evaluate(
        make_intent(
            "deploy_production",
            ("deployment.production",),
        )
    )

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED


@pytest.mark.parametrize(
    "operation",
    [
        "execute_shell",
        "network_request",
        "modify_policy",
        "unknown_operation",
    ],
)
def test_unlisted_operations_do_not_get_implicit_authority(operation):
    decision = engineering_policy().evaluate(
        make_intent(operation, ())
    )

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED


def test_missing_capability_does_not_bypass_policy():
    decision = engineering_policy().evaluate(
        make_intent("write_file", ())
    )

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED
