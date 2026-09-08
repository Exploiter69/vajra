from __future__ import annotations

from vajra.policy.contracts import PolicyDecisionType
from vajra.policy.evaluator import PolicyEvaluator, PolicyRule


ENGINEERING_POLICY_ID = "engineering-v0"
ENGINEERING_POLICY_VERSION = "1"


def _build_rules() -> tuple[PolicyRule, ...]:
    return (
        PolicyRule(
            rule_id="read-file",
            operation="read_file",
            decision=PolicyDecisionType.ALLOW,
            reason="Reading workspace files is allowed",
            required_capabilities=("workspace.read",),
        ),
        PolicyRule(
            rule_id="write-file",
            operation="write_file",
            decision=PolicyDecisionType.ALLOW,
            reason="Writing workspace files is allowed",
            required_capabilities=("workspace.write",),
        ),
        PolicyRule(
            rule_id="run-tests",
            operation="run_tests",
            decision=PolicyDecisionType.ALLOW,
            reason="Running verification tests is allowed",
            required_capabilities=("execution.test",),
        ),
        PolicyRule(
            rule_id="run-build",
            operation="run_build",
            decision=PolicyDecisionType.ALLOW,
            reason="Running project builds is allowed",
            required_capabilities=("execution.build",),
        ),
        PolicyRule(
            rule_id="git-push",
            operation="git_push",
            decision=PolicyDecisionType.HUMAN_REQUIRED,
            reason="Pushing repository changes requires human authority",
            required_capabilities=("git.write",),
        ),
        PolicyRule(
            rule_id="force-push",
            operation="git_force_push",
            decision=PolicyDecisionType.DENY,
            reason="Force pushing is prohibited by the engineering policy",
            required_capabilities=("git.write",),
        ),
        PolicyRule(
            rule_id="delete-repository",
            operation="delete_repository",
            decision=PolicyDecisionType.DENY,
            reason="Repository deletion is prohibited by the engineering policy",
            required_capabilities=("repository.admin",),
        ),
        PolicyRule(
            rule_id="deploy-production",
            operation="deploy_production",
            decision=PolicyDecisionType.HUMAN_REQUIRED,
            reason="Production deployment requires human authority",
            required_capabilities=("deployment.production",),
        ),
    )


def engineering_policy() -> PolicyEvaluator:
    """Return the canonical v0 engineering policy evaluator."""
    return PolicyEvaluator(
        policy_id=ENGINEERING_POLICY_ID,
        policy_version=ENGINEERING_POLICY_VERSION,
        rules=_build_rules(),
    )
