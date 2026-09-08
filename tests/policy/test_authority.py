import pytest

from vajra.policy import Intent, PolicyDecisionType
from vajra.policy.authority import PolicyAuthority
from vajra.policy.evaluator import PolicyEvaluator, PolicyRule


def make_intent() -> Intent:
    return Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="write_file",
        parameters={"path": "src/example.py"},
        requested_capabilities=("workspace.write",),
    )


def make_authority() -> PolicyAuthority:
    evaluator = PolicyEvaluator(
        policy_id="engineering-v0",
        policy_version="1",
        rules=(
            PolicyRule(
                rule_id="write",
                operation="write_file",
                decision=PolicyDecisionType.ALLOW,
                reason="Workspace writes are allowed",
                required_capabilities=("workspace.write",),
            ),
        ),
    )
    return PolicyAuthority(evaluator)


def test_authority_returns_policy_decision():
    decision = make_authority().authorize(make_intent())

    assert decision.intent_id == "intent-1"
    assert decision.decision is PolicyDecisionType.ALLOW
    assert decision.policy_id == "engineering-v0"
    assert decision.policy_version == "1"


def test_authority_preserves_deny_decision():
    evaluator = PolicyEvaluator(
        policy_id="engineering-v0",
        policy_version="1",
        rules=(
            PolicyRule(
                rule_id="deny",
                operation="delete_repository",
                decision=PolicyDecisionType.DENY,
                reason="Repository deletion is prohibited",
            ),
        ),
    )

    authority = PolicyAuthority(evaluator)

    intent = Intent(
        intent_id="intent-delete",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="delete_repository",
    )

    decision = authority.authorize(intent)

    assert decision.decision is PolicyDecisionType.DENY


def test_authority_preserves_human_required_decision():
    evaluator = PolicyEvaluator(
        policy_id="engineering-v0",
        policy_version="1",
        rules=(
            PolicyRule(
                rule_id="approval",
                operation="git_push",
                decision=PolicyDecisionType.HUMAN_REQUIRED,
                reason="Push requires human authority",
            ),
        ),
    )

    authority = PolicyAuthority(evaluator)

    intent = Intent(
        intent_id="intent-push",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="git_push",
    )

    decision = authority.authorize(intent)

    assert decision.decision is PolicyDecisionType.HUMAN_REQUIRED


def test_authority_does_not_execute_intent():
    executed = False

    def operation_that_must_not_run() -> None:
        nonlocal executed
        executed = True

    # The operation is deliberately stored only as intent data.
    # PolicyAuthority has no execution mechanism.
    intent = make_intent()
    intent.parameters["operation"] = operation_that_must_not_run

    decision = make_authority().authorize(intent)

    assert decision.decision is PolicyDecisionType.ALLOW
    assert executed is False


class BrokenEvaluator:
    def evaluate(self, intent: Intent):
        from vajra.policy import PolicyDecision

        return PolicyDecision(
            intent_id="wrong-intent",
            decision=PolicyDecisionType.ALLOW,
            policy_id="engineering-v0",
            policy_version="1",
            reason="Incorrect result",
        )


def test_authority_rejects_decision_for_different_intent():
    authority = PolicyAuthority(BrokenEvaluator())

    with pytest.raises(RuntimeError, match="different intent"):
        authority.authorize(make_intent())
