from __future__ import annotations

from vajra.policy.contracts import Intent, PolicyDecision
from vajra.policy.evaluator import PolicyEvaluator


class PolicyAuthority:
    """
    VAJRA-owned authority boundary for policy evaluation.

    The authority layer evaluates an Intent and returns the policy decision.
    It never executes the requested operation.
    """

    def __init__(self, evaluator: PolicyEvaluator) -> None:
        self._evaluator = evaluator

    def authorize(self, intent: Intent) -> PolicyDecision:
        decision = self._evaluator.evaluate(intent)

        if decision.intent_id != intent.intent_id:
            raise RuntimeError(
                "Policy evaluator returned a decision for a different intent"
            )

        return decision
