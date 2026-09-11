from __future__ import annotations

import pytest

from vajra.recovery.strategy_loop import StrategyLoopDetector


def test_new_strategy_is_not_a_loop():
    detector = StrategyLoopDetector()

    result = detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )

    assert not result.anti_loop
    assert not result.repeated
    assert not result.oscillating


def test_repeated_strategy_triggers_anti_loop():
    detector = StrategyLoopDetector()

    detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )
    result = detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )

    assert result.repeated
    assert result.anti_loop


def test_oscillating_strategy_triggers_anti_loop():
    detector = StrategyLoopDetector()

    detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )
    detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-b",
    )
    result = detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )

    assert result.oscillating
    assert result.anti_loop


def test_strategy_history_is_scoped_to_run_and_step():
    detector = StrategyLoopDetector()

    detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )
    result = detector.observe(
        run_id="run-2",
        step_id="step-1",
        strategy_id="strategy-a",
    )

    assert not result.repeated
    assert not result.oscillating


def test_strategy_detector_can_reset():
    detector = StrategyLoopDetector()

    detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )
    detector.reset(run_id="run-1", step_id="step-1")

    result = detector.observe(
        run_id="run-1",
        step_id="step-1",
        strategy_id="strategy-a",
    )

    assert not result.anti_loop


def test_strategy_detector_rejects_empty_strategy():
    detector = StrategyLoopDetector()

    with pytest.raises(ValueError, match="strategy_id"):
        detector.observe(
            run_id="run-1",
            step_id="step-1",
            strategy_id="",
        )
