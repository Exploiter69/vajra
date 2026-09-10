from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vajra.domain import Budget, EngineeringRun
from vajra.recovery.budget import BudgetAssessment, BudgetEnforcer, BudgetUsage
from vajra.recovery.progress import (
    NoProgressDetector,
    ProgressAssessment,
    ProgressObservation,
)

from .contracts import DivergenceClass


class LimitAction(str, Enum):
    CONTINUE = "CONTINUE"
    RECOVER = "RECOVER"
    WAIT_HUMAN = "WAIT_HUMAN"
    ABORT = "ABORT"


@dataclass(frozen=True)
class LimitDecision:
    action: LimitAction
    reason: str
    divergence: DivergenceClass
    budget: BudgetAssessment
    progress: ProgressAssessment | None = None


class BoundedAutonomy:
    """
    Control-plane boundary for bounded autonomous continuation.

    This layer evaluates existing budget and no-progress mechanisms. It does
    not execute work, mutate Run state, authorize transitions, or approve
    recovery actions.
    """

    def __init__(
        self,
        *,
        budget_enforcer: BudgetEnforcer | None = None,
        progress_detector: NoProgressDetector | None = None,
    ) -> None:
        self._budget = budget_enforcer or BudgetEnforcer()
        self._progress = progress_detector or NoProgressDetector()

    def assess(
        self,
        run: EngineeringRun,
        budget: Budget,
        usage: BudgetUsage | None = None,
        *,
        progress: ProgressObservation | None = None,
        now=None,
    ) -> LimitDecision:
        budget_assessment = self._budget.assess(
            run,
            budget,
            usage,
            now=now,
        )

        if budget_assessment.exhausted:
            return LimitDecision(
                action=LimitAction.ABORT,
                reason="hard budget limit exhausted",
                divergence=DivergenceClass.BUDGET_DIVERGENCE,
                budget=budget_assessment,
            )

        progress_assessment = None

        if progress is not None:
            progress_assessment = self._progress.observe(progress)

            if progress_assessment.no_progress:
                return LimitDecision(
                    action=LimitAction.WAIT_HUMAN,
                    reason="no-progress threshold reached",
                    divergence=DivergenceClass.UNKNOWN,
                    budget=budget_assessment,
                    progress=progress_assessment,
                )

        return LimitDecision(
            action=LimitAction.CONTINUE,
            reason="bounded continuation permitted",
            divergence=DivergenceClass.NONE,
            budget=budget_assessment,
            progress=progress_assessment,
        )


__all__ = [
    "BoundedAutonomy",
    "LimitAction",
    "LimitDecision",
]
