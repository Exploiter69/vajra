from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vajra.domain import Budget, EngineeringRun
from vajra.recovery.budget import BudgetAssessment, BudgetEnforcer, BudgetUsage
from vajra.recovery.progress import NoProgressDetector, ProgressAssessment, ProgressObservation
from vajra.recovery.strategy_loop import StrategyLoopAssessment, StrategyLoopDetector

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
    strategy: StrategyLoopAssessment | None = None


class BoundedAutonomy:
    """Control-plane boundary for bounded autonomous continuation."""

    def __init__(self, *, budget_enforcer: BudgetEnforcer | None = None,
                 progress_detector: NoProgressDetector | None = None,
                 strategy_detector: StrategyLoopDetector | None = None) -> None:
        self._budget = budget_enforcer or BudgetEnforcer()
        self._progress = progress_detector or NoProgressDetector()
        self._strategy = strategy_detector or StrategyLoopDetector()

    def assess(self, run: EngineeringRun, budget: Budget, usage: BudgetUsage | None = None, *,
               progress: ProgressObservation | None = None, strategy_id: str | None = None, now=None) -> LimitDecision:
        budget_assessment = self._budget.assess(run, budget, usage, now=now)
        if budget_assessment.exhausted:
            return LimitDecision(LimitAction.ABORT, "hard budget limit exhausted", DivergenceClass.BUDGET_DIVERGENCE, budget_assessment)

        progress_assessment = None
        strategy_assessment = None
        # A strategy is an iteration-level signal, not a Run lifecycle tick.
        # Counting it on every control-state poll caused a single valid strategy
        # to trip anti-loop limits before it had produced an observable result.
        if strategy_id is not None and progress is not None:
            strategy_assessment = self._strategy.observe(
                run_id=run.run_id,
                step_id=progress.step_id,
                strategy_id=strategy_id,
            )
            if strategy_assessment.anti_loop:
                return LimitDecision(
                    LimitAction.WAIT_HUMAN,
                    "strategy loop threshold reached",
                    DivergenceClass.UNKNOWN,
                    budget_assessment,
                    strategy= strategy_assessment,
                )

        if progress is not None:
            progress_assessment = self._progress.observe(progress)
            if progress_assessment.no_progress:
                return LimitDecision(
                    LimitAction.WAIT_HUMAN,
                    "no-progress threshold reached",
                    DivergenceClass.UNKNOWN,
                    budget_assessment,
                    progress=progress_assessment,
                    strategy=strategy_assessment,
                )

        return LimitDecision(LimitAction.CONTINUE, "bounded continuation permitted", DivergenceClass.NONE,
                             budget_assessment, progress_assessment, strategy_assessment)


__all__ = ["BoundedAutonomy", "LimitAction", "LimitDecision"]
