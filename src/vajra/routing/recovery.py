from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import TaskProfile
from .router import CapabilityRouter, RoutingError


class RecoveryAction(str, Enum):
    SAME_MODEL_RETRY = "same_model_retry"
    DIFFERENT_STRATEGY = "different_strategy"
    DIFFERENT_MODEL = "different_model"
    DIFFERENT_WORKER = "different_worker"
    HUMAN = "human"


@dataclass(frozen=True)
class RecoveryPlan:
    action: RecoveryAction
    attempt_index: int
    reason: str
    profile: TaskProfile


class RoutingRecovery:
    """Bounded fallback sequence for model/worker failures.

    Recovery proposes the next resource; the normal Policy, Broker, lease,
    and Verification gates remain mandatory for any resulting execution.
    """

    def __init__(self, router: CapabilityRouter, max_same_model_retries: int = 1) -> None:
        if max_same_model_retries < 0:
            raise ValueError("max_same_model_retries must be non-negative")
        self._router = router
        self._max_same_model_retries = max_same_model_retries

    def next(
        self,
        profile: TaskProfile,
        *,
        request_id: str,
        attempt_index: int,
        same_model_failures: int,
        tried_models: frozenset[str] = frozenset(),
        tried_workers: frozenset[str] = frozenset(),
        strategy_changed: bool = False,
    ) -> RecoveryPlan:
        if same_model_failures < self._max_same_model_retries:
            return RecoveryPlan(RecoveryAction.SAME_MODEL_RETRY, attempt_index + 1, "retry the failed model within its bounded retry budget", profile)
        if not strategy_changed:
            alternate = TaskProfile(profile.task, profile.complexity, profile.required_capabilities, profile.preferred_model, profile.strategy_id + ":alternate", profile.max_cost_units)
            return RecoveryPlan(RecoveryAction.DIFFERENT_STRATEGY, attempt_index + 1, "change reasoning strategy before changing resources", alternate)

        # Prefer a fresh worker for the already-tried model before introducing
        # a second model. This preserves the roadmap's separate worker-loss
        # recovery path when model capacity itself is still viable.
        try:
            worker_switch = self._router.select_alternative(request_id, profile, excluded_workers=tried_workers)
        except RoutingError:
            worker_switch = None
        if worker_switch is not None and worker_switch.worker_id not in tried_workers and worker_switch.model.canonical in tried_models:
            return RecoveryPlan(RecoveryAction.DIFFERENT_WORKER, attempt_index + 1, "reuse a viable model on a fresh eligible worker", profile)

        try:
            model_switch = self._router.select_alternative(request_id, profile, excluded_models=tried_models)
        except RoutingError:
            model_switch = None
        if model_switch is not None and model_switch.model.canonical not in tried_models:
            return RecoveryPlan(RecoveryAction.DIFFERENT_MODEL, attempt_index + 1, "select an eligible model not previously tried", profile)
        if worker_switch is not None and worker_switch.worker_id not in tried_workers:
            return RecoveryPlan(RecoveryAction.DIFFERENT_WORKER, attempt_index + 1, "select an eligible worker not previously tried", profile)
        return RecoveryPlan(RecoveryAction.HUMAN, attempt_index + 1, "bounded routing alternatives are exhausted", profile)
