from __future__ import annotations

from types import SimpleNamespace

from vajra.autonomy.loop import _verification_failure_signature


def make_result(*, output_excerpt: str, needle: str = "multiply(6, 7) == 42") -> SimpleNamespace:
    return SimpleNamespace(
        verification_id="criteria-multiply-regression",
        status=SimpleNamespace(value="FAILED"),
        checks=[
            {
                "check": "filesystem_contains",
                "subject": "test_calculator.py",
                "needle": needle,
                "passed": False,
                "output_excerpt": output_excerpt,
            }
        ],
    )


def test_failed_check_signature_ignores_volatile_output() -> None:
    first = _verification_failure_signature((make_result(output_excerpt="line 1"),))
    second = _verification_failure_signature((make_result(output_excerpt="line 2"),))

    assert first is not None
    assert second == first


def test_failed_check_signature_changes_when_acceptance_check_changes() -> None:
    first = _verification_failure_signature((make_result(output_excerpt="failed"),))
    changed = _verification_failure_signature((
        make_result(output_excerpt="failed", needle="add(2, 3) == 5"),
    ))

    assert first is not None
    assert changed is not None
    assert changed != first


def test_successful_verification_has_no_failure_signature() -> None:
    result = make_result(output_excerpt="ok")
    result.status = SimpleNamespace(value="PASSED")
    result.checks[0]["passed"] = True

    assert _verification_failure_signature((result,)) is None
