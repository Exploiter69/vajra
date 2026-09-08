from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from vajra.domain import Budget, EngineeringRun
from vajra.recovery.contracts import Failure, FailureCategory


@dataclass(frozen=True)
class BudgetUsage:
    """
    Externally observed resource usage for one Engineering Run.

    Durable Run state supplies steps and attempts. Other counters are supplied
    by the execution/model/worker boundaries rather than fabricated here.
    """

    model_calls: int = 0
    command_count: int = 0
    output_size: int = 0
    worker_runtime_seconds: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "model_calls",
            "command_count",
            "output_size",
            "worker_runtime_seconds",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")


@dataclass(frozen=True)
class BudgetViolation:
    """
    One deterministic budget-limit violation.
    """

    resource: str
    limit: int
    observed: int

    def __post_init__(self) -> None:
        if not self.resource:
            raise ValueError("resource must not be empty")
        if self.limit < 0:
            raise ValueError("limit must not be negative")
        if self.observed < 0:
            raise ValueError("observed must not be negative")


@dataclass(frozen=True)
class BudgetAssessment:
    """
    Result of evaluating all v0 budget limits.
    """

    exhausted: bool
    violations: tuple[BudgetViolation, ...] = ()


class BudgetEnforcer:
    """
    Deterministic v0 budget evaluator.

    This class does not execute work, mutate Run state, or persist counters.
    It evaluates canonical Run state plus externally supplied usage and
    produces a RESOURCE_EXHAUSTION failure when a limit is exceeded.
    """

    def assess(
        self,
        run: EngineeringRun,
        budget: Budget,
        usage: BudgetUsage | None = None,
        *,
        now: datetime | None = None,
    ) -> BudgetAssessment:
        if run.budget_id != budget.budget_id:
            raise ValueError(
                f"Budget does not belong to run: {run.run_id}"
            )

        usage = usage or BudgetUsage()
        effective_now = now or datetime.now(timezone.utc)

        elapsed_seconds = max(
            0,
            int(
                (
                    effective_now - run.created_at
                ).total_seconds()
            ),
        )

        violations: list[BudgetViolation] = []

        self._check(
            violations,
            "runtime_seconds",
            budget.max_runtime_seconds,
            elapsed_seconds,
        )
        self._check(
            violations,
            "steps",
            budget.max_steps,
            len(run.steps),
        )

        attempt_count = sum(
            len(step.attempts)
            for step in run.steps
        )

        self._check(
            violations,
            "attempts",
            budget.max_attempts,
            attempt_count,
        )
        self._check(
            violations,
            "model_calls",
            budget.max_model_calls,
            usage.model_calls,
        )
        self._check(
            violations,
            "command_count",
            budget.max_command_count,
            usage.command_count,
        )
        self._check(
            violations,
            "output_size",
            budget.max_output_size,
            usage.output_size,
        )
        self._check(
            violations,
            "worker_runtime_seconds",
            budget.max_worker_runtime_seconds,
            usage.worker_runtime_seconds,
        )

        return BudgetAssessment(
            exhausted=bool(violations),
            violations=tuple(violations),
        )

    def failure(
        self,
        run: EngineeringRun,
        budget: Budget,
        usage: BudgetUsage | None = None,
        *,
        failure_id: str,
        now: datetime | None = None,
    ) -> Failure | None:
        assessment = self.assess(
            run,
            budget,
            usage,
            now=now,
        )

        if not assessment.exhausted:
            return None

        details = {
            "budget_id": budget.budget_id,
            "violations": [
                {
                    "resource": violation.resource,
                    "limit": violation.limit,
                    "observed": violation.observed,
                }
                for violation in assessment.violations
            ],
        }

        resources = ", ".join(
            violation.resource
            for violation in assessment.violations
        )

        return Failure(
            failure_id=failure_id,
            run_id=run.run_id,
            step_id=run.current_step_id or "",
            attempt_id=self._current_attempt_id(run),
            category=FailureCategory.RESOURCE_EXHAUSTION,
            message=f"Budget exhausted: {resources}",
            details=details,
        )

    @staticmethod
    def _check(
        violations: list[BudgetViolation],
        resource: str,
        limit: int,
        observed: int,
    ) -> None:
        if limit < 0:
            raise ValueError(f"{resource} limit must not be negative")

        if observed >= limit:
            violations.append(
                BudgetViolation(
                    resource=resource,
                    limit=limit,
                    observed=observed,
                )
            )

    @staticmethod
    def _current_attempt_id(run: EngineeringRun) -> str:
        if run.current_step_id:
            for step in run.steps:
                if step.step_id == run.current_step_id and step.attempts:
                    return step.attempts[-1].attempt_id

        for step in reversed(run.steps):
            if step.attempts:
                return step.attempts[-1].attempt_id

        return "budget-check"


__all__ = [
    "BudgetAssessment",
    "BudgetEnforcer",
    "BudgetUsage",
    "BudgetViolation",
]
