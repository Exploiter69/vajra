from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from vajra.policy.contracts import (
    Intent,
    PolicyDecision,
    PolicyDecisionType,
)


@dataclass(frozen=True)
class PolicyRule:
    """
    Deterministic rule for evaluating an Intent.

    A rule only decides authority. It never executes the requested operation.
    """

    rule_id: str
    operation: str
    decision: PolicyDecisionType
    reason: str
    required_capabilities: tuple[str, ...] = ()
    modifier: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("rule_id must not be empty")
        if not self.operation:
            raise ValueError("operation must not be empty")
        if not self.reason:
            raise ValueError("reason must not be empty")

        if (
            self.decision is PolicyDecisionType.MODIFY
            and self.modifier is None
        ):
            raise ValueError("MODIFY rule requires a modifier")

        if (
            self.decision is not PolicyDecisionType.MODIFY
            and self.modifier is not None
        ):
            raise ValueError(
                "modifier is only valid for MODIFY rules"
            )


class PolicyEvaluator:
    """
    Deterministic policy evaluator.

    Rules are evaluated in declaration order. The first matching rule wins.
    If no rule matches, the Intent requires human authority.

    This class does not execute commands, invoke models, modify repositories,
    or perform network operations.
    """

    def __init__(
        self,
        policy_id: str,
        policy_version: str,
        rules: tuple[PolicyRule, ...],
    ) -> None:
        if not policy_id:
            raise ValueError("policy_id must not be empty")
        if not policy_version:
            raise ValueError("policy_version must not be empty")

        self._policy_id = policy_id
        self._policy_version = policy_version
        self._rules = rules

    def evaluate(self, intent: Intent) -> PolicyDecision:
        for rule in self._rules:
            if rule.operation != intent.operation:
                continue

            if not set(rule.required_capabilities).issubset(
                intent.requested_capabilities
            ):
                continue

            if rule.decision is PolicyDecisionType.MODIFY:
                assert rule.modifier is not None
                modified_parameters = rule.modifier(dict(intent.parameters))
            else:
                modified_parameters = None

            return PolicyDecision(
                intent_id=intent.intent_id,
                decision=rule.decision,
                policy_id=self._policy_id,
                policy_version=self._policy_version,
                reason=rule.reason,
                modified_parameters=modified_parameters,
            )

        return PolicyDecision(
            intent_id=intent.intent_id,
            decision=PolicyDecisionType.HUMAN_REQUIRED,
            policy_id=self._policy_id,
            policy_version=self._policy_version,
            reason="No matching policy rule authorizes this intent",
        )
