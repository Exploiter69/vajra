import pytest

from vajra.policy import Intent, PolicyDecisionType
from vajra.policy.evaluator import PolicyEvaluator, PolicyRule


def make_intent(
    *,
    operation: str = "write_file",
    parameters: dict | None = None,
    capabilities: tuple[str, ...] = ("workspace.write",),
) -> Intent:
    return Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        parameters=parameters or {},
        requested_capabilities=capabilities,
        reason="test",
    )


def make_policy(*rules: PolicyRule) -> PolicyEvaluator:
    return PolicyEvaluator(
        policy_id="engineering-safe",
        policy_version="1",
        rules=rules,
    )


def test_matching_rule_allows_intent():
    policy = make_policy(
        PolicyRule(
            rule_id="allow-write",
            operation="write_file",
            decision=PolicyDecisionType.ALLOW,
            reason="Workspace file writes are allowed",
            required_capabilities=("workspace.write",),
        )
    )

    decision = policy.evaluate(make_intent())

    assert decision.decision is PolicyDecisionType.ALLOW
    assert decision.intent_id == "intent-1"
    assert decision.policy_id == "engineering-safe"
    assert decision.policy_version == "1"


def test_matching_rule_denies_intent():
    policy = make_policy(
        PolicyRule(
            rule_id="deny-delete",
            operation="delete_repository",
            decision=PolicyDecisionType.DENY,
            reason="Repository deletion is prohibited",
        )
    )

    decision = policy.evaluate(
        make_intent(operation="delete_repository")
    )

    assert decision.decision is PolicyDecisionType.DENY
    assert decision.reason == "Repository deletion is prohibited"


def test_matching_rule_requires_human():
    policy = make_policy(
        PolicyRule(
            rule_id="protect-push",
            operation="git_push",
            decision=PolicyDecisionType.HUMAN_REQUIRED,
            reason="Repository mutation requires human authority",
        )
    )

    decision = policy.evaluate(make_intent(operation="git_push"))

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED


def test_modify_rule_returns_modified_parameters():
    policy = make_policy(
        PolicyRule(
            rule_id="restrict-path",
            operation="write_file",
            decision=PolicyDecisionType.MODIFY,
            reason="Writes must remain inside the workspace",
            required_capabilities=("workspace.write",),
            modifier=lambda parameters: {
                **parameters,
                "path": "workspace/" + parameters["path"].lstrip("/"),
            },
        )
    )

    decision = policy.evaluate(
        make_intent(
            parameters={"path": "/src/example.py"}
        )
    )

    assert decision.decision is PolicyDecisionType.MODIFY
    assert decision.modified_parameters == {
        "path": "workspace/src/example.py"
    }


def test_missing_capability_does_not_match_rule():
    policy = make_policy(
        PolicyRule(
            rule_id="allow-write",
            operation="write_file",
            decision=PolicyDecisionType.ALLOW,
            reason="Workspace file writes are allowed",
            required_capabilities=("workspace.write",),
        )
    )

    decision = policy.evaluate(
        make_intent(capabilities=())
    )

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED


def test_first_matching_rule_wins_deterministically():
    policy = make_policy(
        PolicyRule(
            rule_id="first",
            operation="write_file",
            decision=PolicyDecisionType.DENY,
            reason="First rule",
        ),
        PolicyRule(
            rule_id="second",
            operation="write_file",
            decision=PolicyDecisionType.ALLOW,
            reason="Second rule",
        ),
    )

    decision = policy.evaluate(make_intent())

    assert decision.decision is PolicyDecisionType.DENY
    assert decision.reason == "First rule"


def test_unmatched_operation_requires_human():
    policy = make_policy(
        PolicyRule(
            rule_id="allow-test",
            operation="run_tests",
            decision=PolicyDecisionType.ALLOW,
            reason="Tests are allowed",
        )
    )

    decision = policy.evaluate(
        make_intent(operation="unknown_operation")
    )

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED


@pytest.mark.parametrize(
    "field_name",
    ["policy_id", "policy_version"],
)
def test_policy_identity_is_required(field_name):
    values = {
        "policy_id": "engineering-safe",
        "policy_version": "1",
        "rules": (),
    }
    values[field_name] = ""

    with pytest.raises(ValueError, match="must not be empty"):
        PolicyEvaluator(**values)


def test_modify_rule_requires_modifier():
    with pytest.raises(ValueError, match="requires a modifier"):
        PolicyRule(
            rule_id="modify",
            operation="write_file",
            decision=PolicyDecisionType.MODIFY,
            reason="Modify",
        )


def test_non_modify_rule_cannot_have_modifier():
    with pytest.raises(ValueError, match="only valid"):
        PolicyRule(
            rule_id="allow",
            operation="write_file",
            decision=PolicyDecisionType.ALLOW,
            reason="Allow",
            modifier=lambda parameters: parameters,
        )
