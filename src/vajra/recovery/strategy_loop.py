from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyLoopAssessment:
    strategy_id: str
    history: tuple[str, ...]
    repeated: bool
    oscillating: bool
    anti_loop: bool


class StrategyLoopDetector:
    """
    Deterministic detector for repeated or oscillating recovery strategies.

    This component observes strategy identities only. It does not select,
    execute, authorize, or mutate strategies.
    """

    def __init__(self, *, repetition_threshold: int = 2) -> None:
        if repetition_threshold < 2:
            raise ValueError("repetition_threshold must be at least 2")
        self._threshold = repetition_threshold
        self._history: dict[tuple[str, str], list[str]] = {}

    def observe(
        self,
        *,
        run_id: str,
        step_id: str,
        strategy_id: str,
    ) -> StrategyLoopAssessment:
        if not run_id:
            raise ValueError("run_id must not be empty")
        if not step_id:
            raise ValueError("step_id must not be empty")
        if not strategy_id:
            raise ValueError("strategy_id must not be empty")

        key = (run_id, step_id)
        history = self._history.setdefault(key, [])
        history.append(strategy_id)

        repeated = history.count(strategy_id) >= self._threshold

        oscillating = (
            len(history) >= 3
            and history[-1] == history[-3]
            and history[-1] != history[-2]
        )

        return StrategyLoopAssessment(
            strategy_id=strategy_id,
            history=tuple(history),
            repeated=repeated,
            oscillating=oscillating,
            anti_loop=repeated or oscillating,
        )

    def reset(self, *, run_id: str, step_id: str) -> None:
        self._history.pop((run_id, step_id), None)
